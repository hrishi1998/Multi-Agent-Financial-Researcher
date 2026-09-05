import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _parse_sse_frames(buffer: str) -> list[dict]:
    frames: list[dict] = []
    current: dict = {}
    for raw_line in buffer.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            if current.get("event") and current.get("data"):
                current["data"] = json.loads(current["data"])
                frames.append(current)
            current = {}
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.strip()
        if field == "event":
            current["event"] = value
        elif field == "data":
            current["data"] = value
    if current.get("event") and current.get("data"):
        current["data"] = json.loads(current["data"])
        frames.append(current)
    return frames


@pytest.mark.asyncio
async def test_research_lifecycle_completes_with_report():
    async with await _client() as client:
        created = await client.post(
            "/api/v1/research",
            json={"query": "Analyze NVDA Q3-2025"},
        )
        assert created.status_code == 202
        body = created.json()
        assert body["status"] == "running"
        run_id = body["run_id"]
        assert run_id

        status_body = None
        for _ in range(80):
            response = await client.get(f"/api/v1/research/{run_id}")
            assert response.status_code == 200
            status_body = response.json()
            if status_body["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.25)

        assert status_body is not None
        assert status_body["status"] == "completed"
        assert status_body["final_report"] is not None
        assert status_body["final_report"]["ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_sse_stream_emits_typed_agent_events():
    async with await _client() as client:
        created = await client.post(
            "/api/v1/research",
            json={"query": "Analyze NVDA Q3-2025"},
        )
        run_id = created.json()["run_id"]

        buffer = ""
        async with client.stream("GET", f"/api/v1/research/{run_id}/stream", timeout=30.0) as stream:
            async for chunk in stream.aiter_text():
                buffer += chunk
                if "run.completed" in buffer or "run.failed" in buffer:
                    break

        frames = _parse_sse_frames(buffer)
        names = [frame["event"] for frame in frames]
        assert names[0] == "run.started"
        assert "planner.completed" in names
        assert any(name.startswith("research.") and name.endswith(".completed") for name in names)
        assert "quant.completed" in names or "report.completed" in names
        for frame in frames:
            assert frame["data"]["run_id"] == run_id
            assert "event_type" in frame["data"]
            assert "agent" in frame["data"]
            assert "updated_keys" in frame["data"].get("payload", {}) or frame["data"]["agent"] == "run_manager"


@pytest.mark.asyncio
async def test_unknown_run_returns_404():
    async with await _client() as client:
        response = await client.get("/api/v1/research/non-existent-id")
        assert response.status_code == 404
