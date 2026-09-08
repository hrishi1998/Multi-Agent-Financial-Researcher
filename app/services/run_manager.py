import asyncio
import os
import re
from typing import Any, AsyncGenerator, Dict, Optional

from app.api.schemas.events import AgentEvent, EventType
from app.api.schemas.reports import ResearchReport
from app.graph.workflow import get_compiled_graph
from app.infrastructure.cache.semantic import get_semantic_cache, semantic_cache_enabled
from app.memory.long_term import get_research_memory
from app.services.event_adapter import lifecycle_event, map_node_update
from app.services.run_store import create_run_store, new_run_record

_TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")
_TERMINAL = {"completed", "failed", "cancelled"}
_TERMINAL_EVENTS = {
    EventType.RUN_COMPLETED,
    EventType.RUN_FAILED,
    EventType.RUN_CANCELLED,
}


def hitl_enabled() -> bool:
    return os.getenv("ENABLE_HITL") == "1"


class ResearchRunManager:
    """Coordinates graph runs. Redis-backed when REDIS_URL is reachable."""

    def __init__(self, compiled=None, store=None) -> None:
        self._explicit_graph = compiled
        self._store = store
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def _graph(self):
        return self._explicit_graph or get_compiled_graph()

    async def _backend(self):
        if self._store is None:
            self._store = await create_run_store()
        return self._store

    async def start_research_run(self, user_query: str) -> str:
        store = await self._backend()
        record = new_run_record(user_query)
        run_id = record["run_id"]
        async with self._lock:
            await store.create_run(record)
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.RUN_STARTED,
                "Research run started.",
                "RUNNING",
            ),
        )
        if semantic_cache_enabled():
            cached = await self._lookup_cache(user_query)
            if cached is not None:
                await self._complete_from_cache(run_id, cached)
                return run_id
        self._tasks[run_id] = asyncio.create_task(self._execute(run_id, user_query))
        return run_id

    async def stream_run_events(self, run_id: str) -> AsyncGenerator[AgentEvent, None]:
        store = await self._backend()
        try:
            async for event in store.stream_events(run_id):
                yield event
                if event.event_type in _TERMINAL_EVENTS:
                    break
        except asyncio.CancelledError:
            return

    async def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        store = await self._backend()
        record = await store.get_run(run_id)
        if record is None:
            return None
        return {
            "run_id": record["run_id"],
            "status": record["status"],
            "created_at": record["created_at"],
            "final_report": record["final_report"],
            "error": record["error"],
            "thread_id": record["thread_id"],
        }

    async def get_paused_state(self, run_id: str) -> Optional[Dict[str, Any]]:
        status = await self.get_run_status(run_id)
        if status is None:
            return None
        graph = self._graph()
        config = {"configurable": {"thread_id": status["thread_id"]}}
        snapshot = await graph.aget_state(config)
        values = snapshot.values if snapshot else {}
        evidence = values.get("evidence") or []
        validation = values.get("validation_result")
        raw_issues = []
        if validation is not None:
            raw_issues = getattr(validation, "issues", None) or (
                validation.get("issues") if isinstance(validation, dict) else []
            )
        return {
            "run_id": run_id,
            "status": status["status"],
            "next_nodes": list(snapshot.next) if snapshot else [],
            "evidence": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in evidence
            ],
            "validation_result": (
                validation.model_dump(mode="json")
                if hasattr(validation, "model_dump")
                else validation
            ),
            "warnings": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in raw_issues or []
            ],
        }

    async def resume_run(self, run_id: str, human_updates: Optional[Dict[str, Any]] = None) -> bool:
        status = await self.get_run_status(run_id)
        if status is None:
            return False
        if status["status"] in _TERMINAL:
            return False
        store = await self._backend()
        graph = self._graph()
        config = self._langsmith_config(run_id, status.get("query") or "", status["thread_id"])
        if human_updates:
            await graph.aupdate_state(config, self._normalize_human_updates(human_updates))
        await store.update_run(run_id, status="running", error="")
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.HITL_RESUMED,
                "Human analyst resumed the research run.",
                "RUNNING",
            ),
        )
        self._tasks[run_id] = asyncio.create_task(
            self._execute(run_id, status.get("query") or "", resume=True)
        )
        return True

    async def cancel_run(self, run_id: str) -> bool:
        store = await self._backend()
        record = await store.get_run(run_id)
        if record is None:
            return False
        if record["status"] in _TERMINAL:
            return False
        await store.request_cancel(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        await store.update_run(run_id, status="cancelled")
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.RUN_CANCELLED,
                "Research run cancelled.",
                "FAILED",
            ),
        )
        return True

    def _langsmith_config(self, run_id: str, user_query: str, thread_id: str) -> Dict[str, Any]:
        ticker_match = _TICKER_RE.search(user_query or "")
        metadata: Dict[str, Any] = {"run_id": run_id, "query": user_query}
        if ticker_match:
            metadata["ticker"] = ticker_match.group(1)
        return {
            "configurable": {"thread_id": thread_id},
            "run_name": "Financial_Research_Run",
            "metadata": metadata,
            "tags": ["financial-research"],
        }

    def _normalize_human_updates(self, human_updates: Dict[str, Any]) -> Dict[str, Any]:
        updates = dict(human_updates)
        if "evidence" in updates:
            from langgraph.types import Overwrite

            updates["evidence"] = Overwrite(updates["evidence"])
        return updates

    async def _execute(self, run_id: str, user_query: str, resume: bool = False) -> None:
        store = await self._backend()
        record = await store.get_run(run_id)
        if record is None:
            return
        config = self._langsmith_config(run_id, user_query, record["thread_id"])
        inputs: Any
        if resume:
            inputs = None
        else:
            inputs = {
                "user_query": user_query,
                "run_id": run_id,
                "iteration_count": 0,
                "max_iterations": 2,
                "is_validated": False,
            }
        try:
            graph = self._graph()
            async for update in graph.astream(inputs, config, stream_mode="updates"):
                if await store.is_cancelled(run_id):
                    raise asyncio.CancelledError()
                if not isinstance(update, dict):
                    continue
                for node_name, payload in update.items():
                    event = map_node_update(run_id, node_name, payload, 0)
                    await self._publish(run_id, event)

            snapshot = await graph.aget_state(config)
            next_nodes = list(snapshot.next) if snapshot else []
            if hitl_enabled() and "synthesizer" in next_nodes:
                await store.update_run(run_id, status="awaiting_approval")
                await self._publish(
                    run_id,
                    lifecycle_event(
                        run_id,
                        EventType.HITL_PAUSED,
                        "Paused for human analyst approval before synthesis.",
                        "WARNING",
                        payload={"next_nodes": next_nodes},
                    ),
                )
                return

            final_report = snapshot.values.get("final_report") if snapshot else None
            await store.update_run(run_id, status="completed", final_report=final_report)
            await self._archive_report(final_report)
            await self._save_cache(user_query, final_report)
            await self._publish(
                run_id,
                lifecycle_event(
                    run_id,
                    EventType.RUN_COMPLETED,
                    "Research run completed.",
                    "COMPLETED",
                ),
            )
        except asyncio.CancelledError:
            current = await store.get_run(run_id)
            if current and current["status"] != "cancelled":
                await store.update_run(run_id, status="cancelled")
        except Exception as exc:
            await store.update_run(run_id, status="failed", error=str(exc))
            await self._publish(
                run_id,
                lifecycle_event(
                    run_id,
                    EventType.RUN_FAILED,
                    "Research run failed.",
                    "FAILED",
                    payload={"error": str(exc)},
                ),
            )

    async def _lookup_cache(self, user_query: str) -> Optional[ResearchReport]:
        try:
            return await get_semantic_cache().lookup(user_query)
        except Exception:
            return None

    async def _complete_from_cache(self, run_id: str, report: ResearchReport) -> None:
        store = await self._backend()
        await store.update_run(run_id, status="completed", final_report=report)
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.CACHE_HIT,
                "Semantic cache hit; returning stored research report.",
                "COMPLETED",
                payload={"cache_hit": True},
            ),
        )
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.RUN_COMPLETED,
                "Research run completed.",
                "COMPLETED",
                payload={"cache_hit": True},
            ),
        )

    async def _save_cache(self, user_query: str, report: Any) -> None:
        if not semantic_cache_enabled() or report is None:
            return
        try:
            validated = (
                report
                if isinstance(report, ResearchReport)
                else ResearchReport.model_validate(report)
            )
            await get_semantic_cache().save(user_query, validated)
        except Exception:
            return

    async def _archive_report(self, report: Any) -> None:
        if report is None:
            return
        try:
            validated = (
                report
                if isinstance(report, ResearchReport)
                else ResearchReport.model_validate(report)
            )
            await get_research_memory().save_report(validated)
        except Exception:
            return

    async def _publish(self, run_id: str, event: AgentEvent) -> None:
        store = await self._backend()
        event.sequence_number = await store.next_sequence(run_id)
        await store.publish_event(run_id, event)


run_manager = ResearchRunManager()
