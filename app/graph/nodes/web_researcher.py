import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState

SLEEP_SECONDS = 0.6


async def web_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Stub news/web researcher. Emits qualitative Evidence after simulated I/O."""
    plan = state["plan"]
    ticker = plan.ticker if plan else "NVDA"
    await asyncio.sleep(SLEEP_SECONDS)
    return {
        "evidence": [
            Evidence(
                source="Reuters",
                source_type=SourceType.NEWS,
                raw_text=(
                    f"{ticker} data-center demand remains the primary growth driver "
                    "according to recent sell-side commentary."
                ),
                claim="Street narrative continues to center on data-center GPU demand.",
            )
        ],
        "execution_trace": [
            {
                "node": "web_researcher",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
