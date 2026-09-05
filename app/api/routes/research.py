import asyncio
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.schemas.requests import (
    ResearchCreateRequest,
    ResearchRunAcceptedResponse,
    ResearchRunStatusResponse,
)
from app.services.run_manager import ResearchRunManager, run_manager

router = APIRouter(prefix="/research", tags=["research"])


def _manager(request: Request) -> ResearchRunManager:
    return getattr(request.app.state, "run_manager", run_manager)


@router.post("", response_model=ResearchRunAcceptedResponse, status_code=202)
async def start_research(payload: ResearchCreateRequest, request: Request):
    manager = _manager(request)
    run_id = await manager.start_research_run(payload.query)
    return ResearchRunAcceptedResponse(run_id=run_id, status="running")


@router.get("/{run_id}", response_model=ResearchRunStatusResponse)
async def get_research(run_id: str, request: Request):
    status = await _manager(request).get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return ResearchRunStatusResponse(
        run_id=status["run_id"],
        status=status["status"],
        created_at=status["created_at"],
        final_report=status["final_report"],
        error=status["error"],
    )


@router.get("/{run_id}/stream")
async def stream_research(run_id: str, request: Request):
    manager = _manager(request)
    if await manager.get_run_status(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")

    async def event_publisher() -> AsyncGenerator[Dict[str, Any], None]:
        try:
            async for event in manager.stream_run_events(run_id):
                if await request.is_disconnected():
                    break
                yield {
                    "event": event.event_type.value,
                    "id": event.event_id,
                    "data": event.model_dump_json(),
                }
        except asyncio.CancelledError:
            return

    return EventSourceResponse(event_publisher())


@router.post("/{run_id}/cancel")
async def cancel_research(run_id: str, request: Request):
    cancelled = await _manager(request).cancel_run(run_id)
    if not cancelled and await _manager(request).get_run_status(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return {"run_id": run_id, "cancelled": cancelled}
