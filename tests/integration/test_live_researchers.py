import pytest

from app.graph.nodes.financial_researcher import financial_researcher_node
from app.graph.nodes.market_researcher import market_researcher_node
from app.graph.state import ResearchPlan, ResearchState


def _live_state() -> ResearchState:
    return {
        "run_id": "test-live-aapl",
        "user_query": "Analyze AAPL latest quarter",
        "plan": ResearchPlan(
            ticker="AAPL",
            company_name="Apple Inc.",
            periods_to_fetch=["Q3-2025"],
            required_raw_metrics=["Revenue", "GrossProfit"],
            target_questions=["Analyze AAPL latest quarter"],
        ),
        "evidence": [],
        "raw_financial_data": [],
        "market_data": {},
        "qualitative_evidence": [],
        "rag_context": [],
        "calculated_metrics": {},
        "validation_result": None,
        "retry_count": 0,
        "iteration_count": 0,
        "max_iterations": 2,
        "is_validated": False,
        "execution_trace": [],
        "final_report": None,
        "events": [],
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_financial_researcher_fetches_sec_evidence():
    result = await financial_researcher_node(_live_state())

    assert "evidence" in result
    assert result["execution_trace"]
    if result["evidence"]:
        assert all(item.source == "SEC EDGAR" for item in result["evidence"])
        assert {item.metric for item in result["evidence"]} <= {"Revenue", "GrossProfit"}
        assert result["execution_trace"][0]["status"] == "completed"
    else:
        assert result["execution_trace"][0]["status"] == "failed"
        assert result["execution_trace"][0].get("error")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_market_researcher_fetches_yahoo_quote():
    result = await market_researcher_node(_live_state())

    assert "evidence" in result
    assert result["execution_trace"]
    if result["evidence"]:
        metrics = {item.metric for item in result["evidence"]}
        assert all(item.source == "Yahoo Finance" for item in result["evidence"])
        assert "Price" in metrics
        assert "MarketCap" in metrics
        assert result["execution_trace"][0]["status"] == "completed"
    else:
        assert result["execution_trace"][0]["status"] == "failed"
        assert result["execution_trace"][0].get("error")
