import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState

SLEEP_SECONDS = 0.2


async def rag_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Stub internal-document RAG researcher. Emits Evidence after simulated I/O."""
    plan = state["plan"]
    ticker = plan.ticker if plan else "NVDA"
    await asyncio.sleep(SLEEP_SECONDS)
    return {
        "evidence": [
            Evidence(
                source="Internal Research Memo",
                source_type=SourceType.INTERNAL_DOCUMENT,
                raw_text=(
                    f"Prior coverage notes {ticker} gross margin expansion is tightly "
                    "linked to Hopper/Blackwell mix."
                ),
                claim="Internal memo ties margin expansion to product mix.",
                confidence=0.85,
            )
        ],
        "execution_trace": [
            {
                "node": "rag_researcher",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
