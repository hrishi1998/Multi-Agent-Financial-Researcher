import pytest

from app.api.schemas.reports import SourceType
from app.graph.nodes.rag_researcher import rag_researcher_node
from app.graph.state import ResearchPlan, ResearchState
from app.rag.schemas import DocumentMetadata
from app.tools.rag import RAGRetrieverTool, set_rag_tool


def _state(ticker: str, period: str = "Q3-2025") -> ResearchState:
    return {
        "run_id": f"test-rag-{ticker}",
        "user_query": f"Analyze {ticker} {period}",
        "plan": ResearchPlan(
            ticker=ticker,
            company_name="Apple Inc." if ticker == "AAPL" else ticker,
            periods_to_fetch=[period],
            required_raw_metrics=["Revenue", "GrossProfit"],
            target_questions=[f"Analyze {ticker} {period}"],
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


@pytest.fixture
async def aapl_retriever():
    tool = RAGRetrieverTool()
    await tool.ingest(
        (
            "AAPL Q3-2025 10-Q. Services revenue accelerated and installed base "
            "reached a new high. Gross margin expanded on mix.\n"
            "| Line | USD |\n| Services | 24900000000 |\n"
        ),
        DocumentMetadata(
            ticker="AAPL",
            company_name="Apple Inc.",
            document_type="10-Q",
            financial_period="Q3-2025",
            publication_date="2025-08-01",
        ),
    )
    await tool.ingest(
        (
            "AAPL Q1-2022 10-Q. Supply constraints weighed on iPhone units "
            "and channel inventory remained elevated."
        ),
        DocumentMetadata(
            ticker="AAPL",
            company_name="Apple Inc.",
            document_type="10-Q",
            financial_period="Q1-2022",
            publication_date="2022-04-28",
        ),
    )
    set_rag_tool(tool)
    yield tool
    set_rag_tool(None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_temporal_filter_prioritizes_requested_period(aapl_retriever):
    results = await aapl_retriever.search(
        query="iPhone services revenue gross margin",
        ticker="AAPL",
        period="Q3-2025",
        top_k=3,
    )

    assert results
    assert results[0].metadata.financial_period == "Q3-2025"
    assert results[0].temporal_warning is None
    stale = [chunk for chunk in results if chunk.metadata.financial_period != "Q3-2025"]
    assert all(chunk.temporal_warning for chunk in stale)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rag_researcher_emits_temporally_anchored_evidence(aapl_retriever):
    result = await rag_researcher_node(_state("AAPL", "Q3-2025"))

    assert result["evidence"]
    for item in result["evidence"]:
        assert item.source_type == SourceType.INTERNAL_DOCUMENT
        assert item.temporal_anchor == "Q3-2025"
        assert item.reporting_period == "Q3-2025"
        assert item.raw_text
    assert result["execution_trace"][0]["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rag_researcher_empty_search_is_graceful(aapl_retriever):
    result = await rag_researcher_node(_state("UNKNOWN_CO", "Q3-2025"))

    assert result["evidence"] == []
    assert result["execution_trace"][0]["status"] == "completed"
    assert result["execution_trace"][0]["note"] == "no historical documents indexed"
