import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import verify_api_key
from app.api.schemas.requests import BatchAcceptedResponse, BatchCreateRequest
from app.services.batch_service import BatchResearchManager

router = APIRouter(
    prefix="/research",
    tags=["batch"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/batch", response_model=BatchAcceptedResponse, status_code=202)
async def start_batch(payload: BatchCreateRequest, request: Request):
    batch_id = str(uuid4())
    manager = BatchResearchManager()
    task = asyncio.create_task(
        manager.execute_batch(
            tickers=payload.tickers,
            query_template=payload.query_template,
            output_dir=payload.output_dir,
            batch_id=batch_id,
        )
    )
    jobs = getattr(request.app.state, "batch_jobs", None)
    if jobs is None:
        jobs = {}
        request.app.state.batch_jobs = jobs
    jobs[batch_id] = task
    return BatchAcceptedResponse(
        batch_id=batch_id,
        status="accepted",
        tickers=[ticker.strip().upper() for ticker in payload.tickers],
    )
