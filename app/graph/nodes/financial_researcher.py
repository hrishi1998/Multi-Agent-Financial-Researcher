import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState

SLEEP_SECONDS = 0.5


async def financial_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Stub SEC filing researcher. Emits quantitative Evidence after simulated I/O."""
    plan = state["plan"]
    period = plan.periods_to_fetch[0] if plan and plan.periods_to_fetch else "Q3-2025"
    await asyncio.sleep(SLEEP_SECONDS)
    return {
        "evidence": [
            Evidence(
                source="SEC EDGAR",
                source_type=SourceType.FILING,
                reporting_period=period,
                metric="Revenue",
                value=35_082_000_000.0,
                claim="NVDA reported Q3 revenue of $35.082B.",
            ),
            Evidence(
                source="SEC EDGAR",
                source_type=SourceType.FILING,
                reporting_period=period,
                metric="GrossProfit",
                value=26_090_000_000.0,
                claim="NVDA reported Q3 gross profit of $26.090B.",
            ),
        ],
        "execution_trace": [
            {
                "node": "financial_researcher",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
