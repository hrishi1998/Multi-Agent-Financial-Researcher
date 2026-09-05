from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.reports import ResearchReport


class ResearchCreateRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        examples=["Evaluate NVIDIA's profitability and revenue growth over the last 4 quarters"],
    )


class ResearchRunAcceptedResponse(BaseModel):
    run_id: str
    status: str = "running"


class ResearchRunStatusResponse(BaseModel):
    run_id: str
    status: str
    created_at: datetime
    final_report: Optional[ResearchReport] = None
    error: Optional[str] = None
