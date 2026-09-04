from datetime import datetime, timezone
from typing import Any, Dict

from app.graph.state import ResearchState


async def synthesizer_node(state: ResearchState) -> Dict[str, Any]:
    """Deterministic fan-in stub: summarize gathered Evidence without an LLM."""
    evidence = state.get("evidence") or []
    plan = state.get("plan")
    ticker = plan.ticker if plan else "UNKNOWN"
    period = plan.periods_to_fetch[0] if plan and plan.periods_to_fetch else None

    by_source: Dict[str, int] = {}
    for item in evidence:
        by_source[item.source] = by_source.get(item.source, 0) + 1

    final_report = {
        "ticker": ticker,
        "analysis_period": period,
        "evidence_count": len(evidence),
        "by_source": by_source,
        "summary": f"Aggregated {len(evidence)} evidence items for {ticker}.",
    }
    return {
        "final_report": final_report,
        "execution_trace": [
            {
                "node": "synthesizer",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
