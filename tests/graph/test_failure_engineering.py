import httpx
import pytest

from app.api.schemas.reports import RawMetric, SourceType
from app.graph.nodes.financial_researcher import financial_researcher_node
from app.graph.state import ResearchPlan, ResearchState
from app.graph.workflow import graph
from app.tools.market_data import MarketDataClient
from app.tools.sec import SECClient
from app.tools.web_search import WebSearchClient


def _state(ticker: str = "NVDA") -> ResearchState:
    return {
        "run_id": "test-failure-engineering",
        "user_query": f"Analyze {ticker}",
        "plan": ResearchPlan(
            ticker=ticker,
            company_name=ticker,
            periods_to_fetch=["Q3-2025"],
            required_raw_metrics=["Revenue", "GrossProfit"],
            target_questions=[f"Analyze {ticker}"],
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
async def test_sec_429_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    attempts = {"n": 0}

    async def flaky(self, ticker: str, periods_count: int = 4):
        attempts["n"] += 1
        if attempts["n"] == 1:
            request = httpx.Request("GET", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000000.json")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)
        return [
            RawMetric(name="Revenue", period="Q3-2025", value=1_000.0, source_filing="10-Q"),
            RawMetric(name="GrossProfit", period="Q3-2025", value=400.0, source_filing="10-Q"),
        ]

    monkeypatch.setattr(SECClient, "get_quarterly_financials", flaky)
    result = await financial_researcher_node(_state("NVDA"))

    assert attempts["n"] == 2
    assert result["execution_trace"][0]["status"] == "completed"
    assert {item.metric for item in result["evidence"]} == {"Revenue", "GrossProfit"}


@pytest.mark.asyncio
async def test_partial_researcher_dropout_still_completes(monkeypatch: pytest.MonkeyPatch):
    async def timeout_quote(self, ticker: str):
        raise httpx.ReadTimeout("market provider timeout")

    async def timeout_news(self, ticker: str, query: str, max_results: int = 3):
        raise httpx.ReadTimeout("web provider timeout")

    monkeypatch.setattr(MarketDataClient, "fetch_quote", timeout_quote)
    monkeypatch.setattr(WebSearchClient, "search_company_news", timeout_news)

    result = await graph.ainvoke(
        {"user_query": "Analyze NVDA Q3-2025", "iteration_count": 0, "max_iterations": 2},
        {"configurable": {"thread_id": "test_partial_dropout_001"}},
    )

    sources = {item.source for item in result["evidence"]}
    assert "SEC EDGAR" in sources
    assert not any(item.source_type == SourceType.MARKET_API for item in result["evidence"])
    assert result["final_report"] is not None
    warnings = result["final_report"].data_quality_warnings
    assert warnings
    assert any("market" in warning.lower() for warning in warnings)
    validator_entries = [entry for entry in result["execution_trace"] if entry["node"] == "validator"]
    assert any(entry["status"] == "warning" for entry in validator_entries)
    assert result["execution_trace"][-1]["node"] == "formatter"


@pytest.mark.asyncio
async def test_non_retryable_invalid_ticker_does_not_loop(monkeypatch: pytest.MonkeyPatch):
    attempts = {"n": 0}

    async def not_found(self, ticker: str, periods_count: int = 4):
        attempts["n"] += 1
        request = httpx.Request("GET", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000000.json")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    monkeypatch.setattr(SECClient, "get_quarterly_financials", not_found)

    result = await graph.ainvoke(
        {
            "user_query": "Analyze INVALID_TICKER_999",
            "iteration_count": 0,
            "max_iterations": 2,
        },
        {"configurable": {"thread_id": "test_invalid_ticker_001"}},
    )

    assert result["plan"].ticker == "INVALID_TICKER_999"
    assert attempts["n"] == 2
    assert result["final_report"] is not None
    assert any("SEC" in warning or "filing" in warning.lower() for warning in result["final_report"].data_quality_warnings)
    assert result["iteration_count"] == 2
