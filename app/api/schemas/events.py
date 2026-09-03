from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import uuid


class EventType(str, Enum):
    # Lifecycle
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"

    # Planner
    PLANNER_STARTED = "planner.started"
    PLANNER_COMPLETED = "planner.completed"

    # Parallel Evidence Gathering
    RESEARCH_FINANCIAL_STARTED = "research.financial.started"
    RESEARCH_FINANCIAL_COMPLETED = "research.financial.completed"
    RESEARCH_MARKET_STARTED = "research.market.started"
    RESEARCH_MARKET_COMPLETED = "research.market.completed"
    RESEARCH_WEB_STARTED = "research.web.started"
    RESEARCH_WEB_COMPLETED = "research.web.completed"
    RESEARCH_RAG_STARTED = "research.rag.started"
    RESEARCH_RAG_COMPLETED = "research.rag.completed"

    # Validation & Recovery
    VALIDATION_STARTED = "validation.started"
    VALIDATION_PASSED = "validation.passed"
    VALIDATION_WARNING = "validation.warning"
    RESEARCH_RETRY = "research.retry"

    # Quant Engine & Synthesis
    QUANT_ANALYSIS_COMPLETED = "quant.completed"
    SYNTHESIS_STARTED = "synthesis.started"
    SYNTHESIS_COMPLETED = "synthesis.completed"
    REPORT_COMPLETED = "report.completed"


class AgentEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent: str
    event_type: EventType
    status: str  # RUNNING, COMPLETED, WARNING, FAILED
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    sequence_number: int = 0
