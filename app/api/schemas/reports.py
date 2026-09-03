from datetime import datetime, timezone
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class RawMetric(BaseModel):
    name: str
    period: str  # e.g., "FY2025Q3" or "2025-09-30"
    value: float
    unit: str = "USD"
    source_filing: str  # e.g., "10-Q Q3 2025"
    accession_number: Optional[str] = None
    confidence: float = 1.0


class CalculatedMetric(BaseModel):
    name: str  # e.g., "Gross Margin", "YoY Revenue Growth"
    formula: str  # e.g., "(Gross Profit / Total Revenue) * 100"
    current_value: float
    previous_value: Optional[float] = None
    change_percentage: Optional[float] = None
    unit: str = "%"


class EvidenceItem(BaseModel):
    claim: str
    observed_facts: List[RawMetric]
    derived_metrics: List[CalculatedMetric]
    source_url_or_filing: str
    excerpt: str
    temporal_anchor: str  # Validates time period consistency
    confidence_score: float = Field(ge=0.0, le=1.0)


class ValidationIssue(BaseModel):
    field: str
    issue_type: str  # "ARITHMETIC_MISMATCH", "PERIOD_INCONSISTENCY", "UNSUPPORTED_CLAIM"
    severity: str  # "CRITICAL", "WARNING"
    description: str
    suggested_action: str


class ValidationResult(BaseModel):
    is_valid: bool
    deterministic_passed: bool
    semantic_passed: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    retry_needed: bool = False
    retry_directive: Optional[str] = None


class ResearchReport(BaseModel):
    run_id: str
    company_name: str
    ticker: str
    analysis_period: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    executive_conclusion: str
    key_findings: List[str]
    bull_case: List[str]
    bear_case: List[str]
    risk_factors: List[str]

    financial_metrics: Dict[str, float]
    derived_metrics: Dict[str, CalculatedMetric]
    evidence_chain: List[EvidenceItem]
    validation_audit: ValidationResult

    aggregate_confidence_score: float = Field(ge=0.0, le=1.0)
    data_quality_warnings: List[str] = Field(default_factory=list)
