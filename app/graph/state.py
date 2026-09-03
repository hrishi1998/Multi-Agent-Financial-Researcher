import operator
from typing import Annotated, Dict, List, Optional, Any
from typing_extensions import TypedDict
from pydantic import BaseModel
from app.api.schemas.events import AgentEvent
from app.api.schemas.reports import (
    RawMetric,
    CalculatedMetric,
    EvidenceItem,
    ValidationResult,
    ResearchReport,
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

    # Final Artifact & Event Bus
    final_report: Optional[ResearchReport]
    events: Annotated[List[AgentEvent], operator.add]
