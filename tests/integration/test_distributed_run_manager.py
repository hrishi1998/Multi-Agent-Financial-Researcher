import os

import pytest

from app.api.schemas.events import EventType
from app.services.event_adapter import lifecycle_event
from app.services.run_manager import ResearchRunManager

DEFAULT_REDIS = "redis://localhost:6379/0"


async def _redis_reachable(url: str) -> bool:
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(url, decode_responses=True)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


@pytest.fixture
async def redis_url():
    url = os.getenv("REDIS_URL") or DEFAULT_REDIS
    if not await _redis_reachable(url):
        pytest.skip("Redis not available")
    previous = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = url
    os.environ["USE_REDIS"] = "1"
    yield url
    if previous is None:
        os.environ.pop("REDIS_URL", None)
    else:
        os.environ["REDIS_URL"] = previous
    os.environ.pop("USE_REDIS", None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_events_stream_across_run_manager_instances(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("USE_REDIS", "1")

    producer = ResearchRunManager()
    consumer = ResearchRunManager()

    async def _fake_execute(self, run_id: str, user_query: str, resume: bool = False) -> None:
        store = await self._backend()
        await store.update_run(run_id, status="completed")
        await self._publish(
            run_id,
            lifecycle_event(
                run_id,
                EventType.RUN_COMPLETED,
                "Research run completed.",
                "COMPLETED",
            ),
        )

    monkeypatch.setattr(ResearchRunManager, "_execute", _fake_execute)

    run_id = await producer.start_research_run("Analyze NVDA Q3-2025")
    remote_status = await consumer.get_run_status(run_id)
    assert remote_status is not None
    assert remote_status["run_id"] == run_id

    collected = []
    async for event in consumer.stream_run_events(run_id):
        collected.append(event)
        if event.event_type in {EventType.RUN_COMPLETED, EventType.RUN_FAILED}:
            break

    names = [event.event_type for event in collected]
    assert EventType.RUN_STARTED in names
    assert EventType.RUN_COMPLETED in names
    assert all(event.run_id == run_id for event in collected)
