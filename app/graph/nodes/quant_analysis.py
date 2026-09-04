from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.schemas.reports import CalculatedMetric, Evidence
from app.graph.state import ResearchState


def calculate_percentage_growth(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / abs(previous)) * 100, 2)


def calculate_margin(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _latest_values(evidence: List[Evidence]) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for item in evidence:
        if item.value is None or not item.metric:
            continue
        values[item.metric] = item.value
    return values


async def quant_analysis_node(state: ResearchState) -> Dict[str, Any]:
    """Compute derived metrics from quantitative Evidence (no LLM)."""
    evidence: List[Evidence] = state.get("evidence") or []
    quantitative = [item for item in evidence if item.value is not None]
    by_metric = _latest_values(quantitative)

    calculated: Dict[str, CalculatedMetric] = {}
    revenue: Optional[float] = by_metric.get("Revenue")
    gross_profit: Optional[float] = by_metric.get("GrossProfit")

    if revenue is not None and gross_profit is not None:
        margin = calculate_margin(gross_profit, revenue)
        calculated["Mock_Margin"] = CalculatedMetric(
            name="Gross Margin",
            formula="(Gross Profit / Revenue) * 100",
            current_value=margin,
            unit="%",
        )
    elif quantitative:
        first = quantitative[0]
        calculated["Mock_Margin"] = CalculatedMetric(
            name="Stub Coverage Ratio",
            formula="value / value * 100",
            current_value=100.0,
            previous_value=first.value,
            unit="%",
        )

    return {
        "calculated_metrics": calculated,
        "execution_trace": [
            {
                "node": "quant_analysis",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
