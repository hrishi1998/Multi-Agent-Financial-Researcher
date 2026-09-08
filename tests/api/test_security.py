import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_research_post_requires_api_key_when_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")

    async with await _client() as client:
        denied = await client.post(
            "/api/v1/research",
            json={"query": "Analyze NVDA Q3-2025"},
        )
        assert denied.status_code == 401

        accepted = await client.post(
            "/api/v1/research",
            json={"query": "Analyze NVDA Q3-2025"},
            headers={"X-API-Key": "secret-test-key"},
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "running"


@pytest.mark.asyncio
async def test_research_get_and_stream_require_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")

    async with await _client() as client:
        created = await client.post(
            "/api/v1/research",
            json={"query": "Analyze NVDA Q3-2025"},
            headers={"X-API-Key": "secret-test-key"},
        )
        run_id = created.json()["run_id"]

        status_denied = await client.get(f"/api/v1/research/{run_id}")
        assert status_denied.status_code == 401

        stream_denied = await client.get(f"/api/v1/research/{run_id}/stream")
        assert stream_denied.status_code == 401

        status_ok = await client.get(
            f"/api/v1/research/{run_id}",
            headers={"X-API-Key": "secret-test-key"},
        )
        assert status_ok.status_code == 200
