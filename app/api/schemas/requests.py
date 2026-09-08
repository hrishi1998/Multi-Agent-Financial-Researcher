from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.api.schemas.reports import Evidence, ResearchReport, ValidationResult


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


class ResearchResumeRequest(BaseModel):
    evidence: Optional[List[Evidence]] = None
    notes: Optional[str] = None


class ResearchPausedStateResponse(BaseModel):
    run_id: str
    status: str
    next_nodes: List[str] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    validation_result: Optional[ValidationResult] = None
    warnings: List[dict] = Field(default_factory=list)
