from datetime import datetime, timezone
from typing import Any, Dict

from app.api.schemas.reports import ResearchReport, ValidationResult
from app.graph.quality import missing_source_warnings
from app.graph.state import ResearchState


def _as_mapping(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, ResearchReport):
        return raw.model_dump()
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if isinstance(raw, dict):
        return raw
    return {}


async def formatter_node(state: ResearchState) -> Dict[str, Any]:
    """Serialize graph state into a strictly validated ResearchReport instance."""
    raw = _as_mapping(state.get("final_report"))
    plan = state.get("plan")
    evidence = state.get("evidence") or []
    calculated_metrics = state.get("calculated_metrics") or {}
    is_valid = bool(state.get("is_validated", False))

    ticker = raw.get("ticker") or (plan.ticker if plan else "NVDA")
    company_name = plan.company_name if plan else "NVIDIA Corporation"
    analysis_period = raw.get("analysis_period") or (
        plan.periods_to_fetch[0] if plan and plan.periods_to_fetch else "Q3-2025"
    )

    financial_metrics: Dict[str, float] = {}
    for item in evidence:
        if item.metric is not None and item.value is not None:
            financial_metrics[item.metric] = item.value

    research_report = ResearchReport.model_validate(
        {
            "run_id": state.get("run_id") or "run-stub",
            "company_name": company_name,
            "ticker": ticker,
            "analysis_period": analysis_period,
            "executive_conclusion": raw.get("summary")
            or f"Deterministic stub report for {ticker} ({analysis_period}).",
            "key_findings": [
                f"{metric.name}: {metric.current_value}{metric.unit}"
                for metric in calculated_metrics.values()
            ]
            or [raw.get("summary") or "No derived metrics."],
            "bull_case": [],
            "bear_case": [],
            "risk_factors": [],
            "financial_metrics": financial_metrics,
            "derived_metrics": calculated_metrics,
            "evidence": evidence,
            "evidence_chain": [],
            "validation_audit": ValidationResult(
                is_valid=is_valid,
                deterministic_passed=is_valid,
                semantic_passed=True,
            ),
            "aggregate_confidence_score": 0.85,
            "data_quality_warnings": missing_source_warnings(evidence),
        }
    )

    return {
        "final_report": research_report,
        "execution_trace": [
            {
                "node": "formatter",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
