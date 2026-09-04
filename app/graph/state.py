import operator
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel
from typing_extensions import TypedDict

from app.api.schemas.events import AgentEvent
from app.api.schemas.reports import (
    CalculatedMetric,
    Evidence,
    EvidenceItem,
    RawMetric,
    ResearchReport,
    ValidationResult,
)


class ResearchPlan(BaseModel):
    ticker: str
    company_name: str
    periods_to_fetch: List[str]  # e.g., ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025"]
    required_raw_metrics: List[str]  # ["Revenue", "GrossProfit", "OperatingIncome", "NetIncome", "EPS"]
    target_questions: List[str]
    max_retries: int = 2


class ResearchState(TypedDict):
    # Run Metadata
    run_id: str
    user_query: str
    plan: Optional[ResearchPlan]

    # Unified fan-in channel for concurrent researchers (SEC, market, web, RAG)
    evidence: Annotated[List[Evidence], operator.add]

    # Concurrent Agent Outputs (Appended via operator.add reducer)
    raw_financial_data: Annotated[List[RawMetric], operator.add]
    market_data: Annotated[Dict[str, Any], operator.add]
    qualitative_evidence: Annotated[List[EvidenceItem], operator.add]
    rag_context: Annotated[List[Dict[str, Any]], operator.add]

    # Deterministic Engine Calculations
    calculated_metrics: Dict[str, CalculatedMetric]

    # Validation and Cyclic Controls
    validation_result: Optional[ValidationResult]
    retry_count: int
    iteration_count: int
    max_iterations: int
    is_validated: bool
    execution_trace: Annotated[List[Dict[str, Any]], operator.add]

    # Final Artifact & Event Bus
    final_report: Optional[ResearchReport]
    events: Annotated[List[AgentEvent], operator.add]
