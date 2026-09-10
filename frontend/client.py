"""HTTP-only client for the research API. No LangGraph, Postgres, or app imports."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx
from pydantic import BaseModel, Field


def api_base_url() -> str:
    raw = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}"


def api_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    api_key = os.getenv("API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


class StreamEvent(BaseModel):
    event_type: str
    message: str = ""
    agent: str = ""
    status: str = ""
    run_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence_number: int = 0


def start_research(query: str) -> str:
    response = httpx.post(
        f"{api_base_url()}/api/v1/research",
        json={"query": query},
        headers=api_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return str(response.json()["run_id"])


def get_run(run_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{api_base_url()}/api/v1/research/{run_id}",
        headers=api_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def get_run_state(run_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{api_base_url()}/api/v1/research/{run_id}/state",
        headers=api_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def resume_run(run_id: str) -> dict[str, Any]:
    response = httpx.post(
        f"{api_base_url()}/api/v1/research/{run_id}/resume",
        json={},
        headers=api_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_sse_frame(raw: str) -> StreamEvent | None:
    event_name = ""
    data_lines: list[str] = []
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalized.split("\n"):
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return None
    try:
        payload = json.loads("\n".join(data_lines))
        if isinstance(payload, str):
            payload = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return StreamEvent(
        event_type=str(payload.get("event_type") or event_name),
        message=str(payload.get("message") or ""),
        agent=str(payload.get("agent") or ""),
        status=str(payload.get("status") or ""),
        run_id=str(payload.get("run_id") or ""),
        payload=payload.get("payload") or {},
        sequence_number=int(payload.get("sequence_number") or 0),
    )


def iter_run_events(run_id: str) -> Iterator[StreamEvent]:
    with httpx.stream(
        "GET",
        f"{api_base_url()}/api/v1/research/{run_id}/stream",
        headers={**api_headers(), "Accept": "text/event-stream"},
        timeout=None,
    ) as response:
        response.raise_for_status()
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                event = parse_sse_frame(frame)
                if event is not None:
                    yield event
        if buffer.strip():
            event = parse_sse_frame(buffer)
            if event is not None:
                yield event
