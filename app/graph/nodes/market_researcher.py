import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState

SLEEP_SECONDS = 0.3


async def market_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Stub market-data researcher. Emits price Evidence after simulated I/O."""
    plan = state["plan"]
    ticker = plan.ticker if plan else "NVDA"
    await asyncio.sleep(SLEEP_SECONDS)
    return {
        "evidence": [
            Evidence(
                source="Yahoo Finance",
                source_type=SourceType.MARKET_API,
                metric="ClosePrice",
                value=148.56,
                claim=f"{ticker} last close was 148.56 USD.",
            )
        ],
        "execution_trace": [
            {
                "node": "market_researcher",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
