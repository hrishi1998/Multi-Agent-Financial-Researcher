import asyncio
from pathlib import Path

import pytest

from app.api.schemas.reports import (
    CalculatedMetric,
    Evidence,
    ResearchReport,
    SourceType,
    ValidationResult,
)
from app.services.batch_service import BatchResearchManager
from app.services.exporter import ReportExporter


def _report(ticker: str = "NVDA", run_id: str = "batch-report-1") -> ResearchReport:
    return ResearchReport(
        run_id=run_id,
        company_name=f"{ticker} Corporation",
        ticker=ticker,
        analysis_period="Q3-2025",
        executive_conclusion=f"{ticker} remains the primary data-center beneficiary.",
        key_findings=["Gross margin expanded on mix.", "Revenue concentration remains high."],
        bull_case=["Sustained accelerator demand."],
        bear_case=["Customer concentration risk."],
        risk_factors=["Export controls."],
        financial_metrics={"Revenue": 35_082_000_000.0},
        derived_metrics={
            "Gross Margin": CalculatedMetric(
                name="Gross Margin",
                formula="(Gross Profit / Revenue) * 100",
                current_value=74.4,
                previous_value=70.1,
                change_percentage=4.3,
                unit="%",
            )
        },
        evidence=[
            Evidence(
                source="SEC 10-Q",
                source_type=SourceType.FILING,
                reporting_period="Q3-2025",
                metric="Revenue",
                value=35_082_000_000.0,
                claim="Revenue printed above the prior-year quarter.",
                raw_text="Revenue was $35.1B in Q3-2025.",
                source_url="https://www.sec.gov/example",
                confidence=0.94,
            )
        ],
        validation_audit=ValidationResult(
            is_valid=True,
            deterministic_passed=True,
            semantic_passed=True,
        ),
        aggregate_confidence_score=0.88,
        data_quality_warnings=["Market feed used a delayed quote."],
    )


def test_report_exporter_renders_expected_markdown_sections():
    markdown = ReportExporter().generate_markdown(_report())

    assert "# NVDA Corporation (NVDA) — Q3-2025" in markdown
    assert "## Executive Summary" in markdown
    assert "primary data-center beneficiary" in markdown
    assert "## Key Findings" in markdown
    assert "Gross margin expanded on mix." in markdown
    assert "## Bull Case" in markdown
    assert "## Bear Case" in markdown
    assert "## Calculated Metrics" in markdown
    assert "Gross Margin" in markdown
    assert "(Gross Profit / Revenue) * 100" in markdown
    assert "## Evidence Citations" in markdown
    assert "SEC 10-Q" in markdown
    assert "Revenue was $35.1B in Q3-2025." in markdown


@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_manager_exports_three_tickers_under_semaphore(tmp_path: Path):
    tickers = ("AAPL", "MSFT", "NVDA")
    reports = {ticker: _report(ticker, run_id=f"batch-{ticker}") for ticker in tickers}

    class StubGraph:
        async def ainvoke(self, inputs, config=None):
            await asyncio.sleep(0.05)
            query = inputs["user_query"]
            ticker = next(key for key in reports if key in query)
            return {"final_report": reports[ticker]}

    exporter = ReportExporter()
    manager = BatchResearchManager(concurrency=2, graph=StubGraph(), exporter=exporter)
    summary = await manager.execute_batch(
        tickers=["AAPL", "MSFT", "NVDA"],
        query_template="Evaluate {ticker} with MockChatModel offline stubs",
        output_dir=str(tmp_path),
        batch_id="offline-batch",
    )

    assert summary.total == 3
    assert summary.succeeded == 3
    assert summary.failed == 0
    assert summary.errors == []
    assert manager.max_in_flight <= 2
    assert manager.max_in_flight >= 1
    written = list(tmp_path.glob("*.md"))
    assert len(written) == 3
    assert {path.name.split("_", maxsplit=1)[0] for path in written} == {"AAPL", "MSFT", "NVDA"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_manager_isolates_per_ticker_failures(tmp_path: Path):
    class FlakyGraph:
        async def ainvoke(self, inputs, config=None):
            if "MSFT" in inputs["user_query"]:
                raise RuntimeError("simulated provider outage")
            return {"final_report": _report("AAPL" if "AAPL" in inputs["user_query"] else "NVDA")}

    manager = BatchResearchManager(concurrency=5, graph=FlakyGraph(), exporter=ReportExporter())
    summary = await manager.execute_batch(
        tickers=["AAPL", "MSFT", "NVDA"],
        output_dir=str(tmp_path),
    )

    assert summary.succeeded == 2
    assert summary.failed == 1
    assert any(error.startswith("MSFT:") for error in summary.errors)
