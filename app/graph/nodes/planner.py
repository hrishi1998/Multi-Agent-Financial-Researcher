import re
from datetime import datetime, timezone
from typing import Any, Dict

from app.graph.state import ResearchPlan, ResearchState

_TICKER_RE = re.compile(r"\b([A-Z]{2,20}(?:_[A-Z0-9]+)*)\b")
_SKIP_TOKENS = {"USD", "SEC", "YOY", "QOQ", "THE", "AND", "FOR"}
_COMPANY_NAMES = {
    "NVDA": "NVIDIA Corporation",
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com, Inc.",
}


def infer_ticker(user_query: str) -> str:
    for token in _TICKER_RE.findall(user_query or ""):
        if token.startswith("Q") and token[1:2].isdigit():
            continue
        if token in _SKIP_TOKENS:
            continue
        return token
    return "NVDA"


async def planner_node(state: ResearchState) -> Dict[str, Any]:
    """Decompose the user query into a structured research plan (deterministic stub)."""
    user_query = state["user_query"]
    ticker = infer_ticker(user_query)
    plan = ResearchPlan(
        ticker=ticker,
        company_name=_COMPANY_NAMES.get(ticker, ticker),
        periods_to_fetch=["Q3-2025"],
        required_raw_metrics=["Revenue", "GrossProfit"],
        target_questions=[user_query],
    )
    return {
        "plan": plan,
        "execution_trace": [
            {
                "node": "planner",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
