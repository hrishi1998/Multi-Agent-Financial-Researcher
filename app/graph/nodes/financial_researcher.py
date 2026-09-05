from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from app.api.schemas.reports import Evidence, RawMetric, SourceType
from app.graph.state import ResearchState
from app.tools.sec import SECClient


def _raw_metric_to_evidence(metric: RawMetric) -> Evidence:
    return Evidence(
        source="SEC EDGAR",
        source_type=SourceType.FILING,
        reporting_period=metric.period,
        metric=metric.name,
        value=metric.value,
        claim=f"{metric.name} of {metric.value} from {metric.source_filing}.",
        confidence=metric.confidence,
    )


async def financial_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Fetch SEC EDGAR facts and normalize them to Evidence. Never crash the graph."""
    plan = state.get("plan")
    ticker = plan.ticker if plan else "AAPL"
    required = set(plan.required_raw_metrics) if plan and plan.required_raw_metrics else set()
    periods_count = len(plan.periods_to_fetch) if plan and plan.periods_to_fetch else 4

    try:
        client = SECClient()
        raw_metrics: List[RawMetric] = await client.get_quarterly_financials(
            ticker, periods_count=max(periods_count, 1)
        )
        if required:
            raw_metrics = [metric for metric in raw_metrics if metric.name in required]
        evidence = [_raw_metric_to_evidence(metric) for metric in raw_metrics]
        return {
            "evidence": evidence,
            "execution_trace": [
                {
                    "node": "financial_researcher",
                    "status": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "items": len(evidence),
                }
            ],
        }
    except (httpx.HTTPError, Exception) as exc:
        return {
            "evidence": [],
            "execution_trace": [
                {
                    "node": "financial_researcher",
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
