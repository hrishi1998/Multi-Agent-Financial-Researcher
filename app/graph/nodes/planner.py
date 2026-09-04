from datetime import datetime, timezone
from typing import Any, Dict

from app.graph.state import ResearchPlan, ResearchState


async def planner_node(state: ResearchState) -> Dict[str, Any]:
    """Decompose the user query into a structured research plan (deterministic stub)."""
    user_query = state["user_query"]
    plan = ResearchPlan(
        ticker="NVDA",
        company_name="NVIDIA Corporation",
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
