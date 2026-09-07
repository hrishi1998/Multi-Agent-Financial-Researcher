from datetime import datetime, timezone
from typing import Any, Dict

from app.graph.state import ResearchPlan, ResearchState
from app.infrastructure.llm.provider import LLMProviderFactory, _infer_company, _infer_periods

PLANNER_SYSTEM_PROMPT = """You are a sell-side financial research planner.
Decompose the user query into a ResearchPlan.
Rules:
- ticker must be a canonical uppercase symbol (NVDA, AAPL, TSLA).
- company_name must be the legal or common issuer name.
- periods_to_fetch must be quarter labels like Q3-2025.
- required_raw_metrics must include Revenue, GrossProfit, OperatingIncome, NetIncome when profitability is in scope.
- target_questions must be focused qualitative queries for web/RAG research.
- Do not invent financial figures. You only plan what to fetch.
"""


async def planner_node(state: ResearchState) -> Dict[str, Any]:
    """LLM-backed query decomposition into a structured ResearchPlan."""
    user_query = state.get("user_query") or ""
    model = LLMProviderFactory.get_chat_model(
        temperature=0.0,
        structured_output_schema=ResearchPlan,
    )
    try:
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "human", "content": user_query},
        ]
        plan = await model.ainvoke(messages)
        if not isinstance(plan, ResearchPlan):
            plan = ResearchPlan.model_validate(plan)
    except Exception:
        ticker, company = _infer_company(user_query)
        plan = ResearchPlan(
            ticker=ticker,
            company_name=company,
            periods_to_fetch=_infer_periods(user_query),
            required_raw_metrics=["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"],
            target_questions=[user_query],
        )

    plan.ticker = plan.ticker.upper().strip()
    return {
        "plan": plan,
        "execution_trace": [
            {
                "node": "planner",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ticker": plan.ticker,
            }
        ],
    }
