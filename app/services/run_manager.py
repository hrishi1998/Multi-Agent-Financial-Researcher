import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4

from app.api.schemas.events import AgentEvent, EventType
from app.graph.workflow import graph as compiled_graph
from app.services.event_adapter import lifecycle_event, map_node_update

_TERMINAL = {"completed", "failed", "cancelled"}
_TERMINAL_EVENTS = {
    EventType.RUN_COMPLETED,
    EventType.RUN_FAILED,
    EventType.RUN_CANCELLED,
}


class ResearchRunManager:
    """Coordinates background graph runs and typed SSE event queues."""

    def __init__(self, compiled=None) -> None:
        self._graph = compiled or compiled_graph
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def start_research_run(self, user_query: str) -> str:
        run_id = str(uuid4())
        record: Dict[str, Any] = {
            "run_id": run_id,
            "status": "running",
            "thread_id": run_id,
            "created_at": datetime.now(timezone.utc),
            "final_report": None,
            "error": None,
            "query": user_query,
            "queue": asyncio.Queue(),
            "cancel_event": asyncio.Event(),
            "sequence": 0,
            "task": None,
        }
        async with self._lock:
            self._runs[run_id] = record
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.RUN_STARTED,
                "Research run started.",
                "RUNNING",
            ),
        )
        record["task"] = asyncio.create_task(self._execute(run_id, user_query))
        return run_id

    async def stream_run_events(self, run_id: str) -> AsyncGenerator[AgentEvent, None]:
        record = self._runs.get(run_id)
        if record is None:
            raise KeyError(run_id)
        queue: asyncio.Queue = record["queue"]
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    if record["status"] in _TERMINAL and queue.empty():
                        break
                    continue
                yield event
                if event.event_type in _TERMINAL_EVENTS:
                    break
        except asyncio.CancelledError:
            return

    async def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        record = self._runs.get(run_id)
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

    async def cancel_run(self, run_id: str) -> bool:
        record = self._runs.get(run_id)
        if record is None:
            return False
        if record["status"] in _TERMINAL:
            return False
        record["cancel_event"].set()
        task = record.get("task")
        if task and not task.done():
            task.cancel()
        record["status"] = "cancelled"
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

    async def _execute(self, run_id: str, user_query: str) -> None:
        record = self._runs[run_id]
        config = {"configurable": {"thread_id": record["thread_id"]}}
        inputs = {
            "user_query": user_query,
            "run_id": run_id,
            "iteration_count": 0,
            "max_iterations": 2,
            "is_validated": False,
        }
        try:
            async for update in self._graph.astream(
                inputs, config, stream_mode="updates"
            ):
                if record["cancel_event"].is_set():
                    raise asyncio.CancelledError()
                if not isinstance(update, dict):
                    continue
                for node_name, payload in update.items():
                    event = map_node_update(
                        run_id, node_name, payload, record["sequence"] + 1
                    )
                    await self._publish(run_id, event)

            snapshot = self._graph.get_state(config)
            record["final_report"] = snapshot.values.get("final_report")
            record["status"] = "completed"
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
            record["status"] = "cancelled"
            if record["queue"].empty():
                await self._publish(
                    run_id,
                    lifecycle_event(
                        run_id,
                        EventType.RUN_CANCELLED,
                        "Research run cancelled.",
                        "FAILED",
                    ),
                )
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
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

    async def _publish(self, run_id: str, event: AgentEvent) -> None:
        record = self._runs[run_id]
        record["sequence"] += 1
        event.sequence_number = record["sequence"]
        await record["queue"].put(event)


run_manager = ResearchRunManager()
