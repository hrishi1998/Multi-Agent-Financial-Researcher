import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4

from app.api.schemas.events import AgentEvent


def use_redis() -> bool:
    if not os.getenv("REDIS_URL"):
        return False
    if os.getenv("USE_REDIS") == "1":
        return True
    return os.getenv("PYTEST_CURRENT_TEST") is None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_report(report: Any) -> Optional[str]:
    if report is None:
        return None
    if hasattr(report, "model_dump"):
        return json.dumps(report.model_dump(mode="json"))
    return json.dumps(report)


def deserialize_report(raw: Any) -> Any:
    if raw in (None, "", "null"):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_run(self, record: Dict[str, Any]) -> None:
        async with self._lock:
            record.setdefault("queue", asyncio.Queue())
            record.setdefault("cancel_event", asyncio.Event())
            record.setdefault("sequence", 0)
            self._runs[record["run_id"]] = record

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        record = self._runs.get(run_id)
        if record is None:
            return None
        return _public_record(record)

    async def update_run(self, run_id: str, **fields: Any) -> None:
        record = self._runs.get(run_id)
        if record is None:
            return
        record.update(fields)

    async def next_sequence(self, run_id: str) -> int:
        record = self._runs[run_id]
        record["sequence"] = int(record.get("sequence") or 0) + 1
        return int(record["sequence"])

    async def publish_event(self, run_id: str, event: AgentEvent) -> None:
        record = self._runs[run_id]
        await record["queue"].put(event)

    async def stream_events(self, run_id: str) -> AsyncGenerator[AgentEvent, None]:
        record = self._runs.get(run_id)
        if record is None:
            raise KeyError(run_id)
        queue: asyncio.Queue = record["queue"]
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                if record.get("status") in {"completed", "failed", "cancelled"} and queue.empty():
                    break
                continue
            yield event
            if event.event_type.value in {"run.completed", "run.failed", "run.cancelled"}:
                break

    async def request_cancel(self, run_id: str) -> None:
        record = self._runs.get(run_id)
        if record is not None:
            record["cancel_event"].set()

    async def is_cancelled(self, run_id: str) -> bool:
        record = self._runs.get(run_id)
        return bool(record and record["cancel_event"].is_set())


class RedisRunStore:
    def __init__(self, client: Any) -> None:
        self._redis = client

    def _key(self, run_id: str) -> str:
        return f"run:{run_id}"

    def _events_key(self, run_id: str) -> str:
        return f"run:{run_id}:events"

    def _channel(self, run_id: str) -> str:
        return f"run_events:{run_id}"

    def _cancel_key(self, run_id: str) -> str:
        return f"run:{run_id}:cancel"

    async def create_run(self, record: Dict[str, Any]) -> None:
        created = record.get("created_at")
        if isinstance(created, datetime):
            created_at = created.isoformat()
        else:
            created_at = created or _now_iso()
        mapping = {
            "run_id": record["run_id"],
            "status": record.get("status") or "running",
            "thread_id": record.get("thread_id") or record["run_id"],
            "created_at": created_at,
            "final_report": serialize_report(record.get("final_report")) or "",
            "error": record.get("error") or "",
            "query": record.get("query") or "",
            "sequence": "0",
        }
        await self._redis.hset(self._key(record["run_id"]), mapping=mapping)
        await self._redis.expire(self._key(record["run_id"]), 86400)

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        data = await self._redis.hgetall(self._key(run_id))
        if not data:
            return None
        created_raw = data.get("created_at") or _now_iso()
        try:
            created_at = datetime.fromisoformat(created_raw)
        except ValueError:
            created_at = datetime.now(timezone.utc)
        return {
            "run_id": data.get("run_id") or run_id,
            "status": data.get("status") or "running",
            "thread_id": data.get("thread_id") or run_id,
            "created_at": created_at,
            "final_report": deserialize_report(data.get("final_report")),
            "error": data.get("error") or None,
            "query": data.get("query") or "",
            "sequence": int(data.get("sequence") or 0),
        }

    async def update_run(self, run_id: str, **fields: Any) -> None:
        mapping: Dict[str, str] = {}
        if "status" in fields:
            mapping["status"] = str(fields["status"])
        if "error" in fields:
            mapping["error"] = str(fields["error"] or "")
        if "final_report" in fields:
            mapping["final_report"] = serialize_report(fields["final_report"]) or ""
        if "query" in fields:
            mapping["query"] = str(fields["query"] or "")
        if "thread_id" in fields:
            mapping["thread_id"] = str(fields["thread_id"])
        if mapping:
            await self._redis.hset(self._key(run_id), mapping=mapping)

    async def next_sequence(self, run_id: str) -> int:
        return int(await self._redis.hincrby(self._key(run_id), "sequence", 1))

    async def publish_event(self, run_id: str, event: AgentEvent) -> None:
        payload = event.model_dump_json()
        await self._redis.rpush(self._events_key(run_id), payload)
        await self._redis.expire(self._events_key(run_id), 86400)
        await self._redis.publish(self._channel(run_id), payload)

    async def stream_events(self, run_id: str) -> AsyncGenerator[AgentEvent, None]:
        if not await self._redis.exists(self._key(run_id)):
            raise KeyError(run_id)
        seen: set[str] = set()
        for raw in await self._redis.lrange(self._events_key(run_id), 0, -1):
            event = AgentEvent.model_validate_json(raw)
            seen.add(event.event_id)
            yield event
            if event.event_type.value in {"run.completed", "run.failed", "run.cancelled"}:
                return

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(run_id))
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.25)
                if message and message.get("type") == "message":
                    event = AgentEvent.model_validate_json(message["data"])
                    if event.event_id in seen:
                        continue
                    seen.add(event.event_id)
                    yield event
                    if event.event_type.value in {"run.completed", "run.failed", "run.cancelled"}:
                        return
                    continue
                record = await self.get_run(run_id)
                if record and record["status"] in {"completed", "failed", "cancelled"}:
                    return
        finally:
            await pubsub.unsubscribe(self._channel(run_id))
            await pubsub.aclose()

    async def request_cancel(self, run_id: str) -> None:
        await self._redis.set(self._cancel_key(run_id), "1", ex=86400)

    async def is_cancelled(self, run_id: str) -> bool:
        return bool(await self._redis.get(self._cancel_key(run_id)))


def _public_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": record["run_id"],
        "status": record["status"],
        "thread_id": record["thread_id"],
        "created_at": record["created_at"],
        "final_report": record.get("final_report"),
        "error": record.get("error"),
        "query": record.get("query"),
        "sequence": record.get("sequence", 0),
    }


_redis_client: Any = None


async def get_redis_client():
    global _redis_client
    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL is required for the Redis run store.")
    if _redis_client is None:
        from redis.asyncio import Redis

        _redis_client = Redis.from_url(url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def create_run_store():
    if not use_redis():
        return InMemoryRunStore()
    try:
        client = await get_redis_client()
        await asyncio.wait_for(client.ping(), timeout=2)
        return RedisRunStore(client)
    except Exception:
        return InMemoryRunStore()


def new_run_record(user_query: str) -> Dict[str, Any]:
    run_id = str(uuid4())
    return {
        "run_id": run_id,
        "status": "running",
        "thread_id": run_id,
        "created_at": datetime.now(timezone.utc),
        "final_report": None,
        "error": None,
        "query": user_query,
        "sequence": 0,
    }
