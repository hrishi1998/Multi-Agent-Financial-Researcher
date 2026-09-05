import pytest

from app.api.schemas.reports import RawMetric
from app.rag.schemas import DocumentMetadata
from app.tools.market_data import MarketQuote
from app.tools.rag import RAGRetrieverTool, set_rag_tool
from app.tools.sec import SECClient


@pytest.fixture(autouse=True)
async def seed_rag_corpus() -> None:
    tool = RAGRetrieverTool()
    await tool.ingest(
        "NVDA Q3-2025 internal memo: gross margin expansion is tied to Hopper/Blackwell mix.",
        DocumentMetadata(
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            document_type="earnings_call",
            financial_period="Q3-2025",
            publication_date="2025-08-28",
        ),
    )
    set_rag_tool(tool)
    yield
    set_rag_tool(None)


@pytest.fixture(autouse=True)
def mock_live_research_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_financials(self: SECClient, ticker: str, periods_count: int = 4):
        return [
            RawMetric(
                name="Revenue",
                period="Q3-2025",
                value=35_082_000_000.0,
                source_filing="10-Q",
            ),
            RawMetric(
                name="GrossProfit",
                period="Q3-2025",
                value=26_090_000_000.0,
                source_filing="10-Q",
            ),
        ]

    async def _fake_quote(self, ticker: str) -> MarketQuote:
        return MarketQuote(
            ticker=ticker,
            regular_market_price=148.56,
            regular_market_volume=12_345_678.0,
            market_cap=2_400_000_000_000.0,
            trailing_pe=28.4,
        )

    monkeypatch.setattr(SECClient, "get_quarterly_financials", _fake_financials)
    monkeypatch.setattr("app.tools.market_data.MarketDataClient.fetch_quote", _fake_quote)
