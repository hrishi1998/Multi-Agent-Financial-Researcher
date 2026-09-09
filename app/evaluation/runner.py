import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.api.schemas.reports import RawMetric, ResearchReport
from app.evaluation.citation_faithfulness import (
    CitationAuditResult,
    CitationFaithfulnessEvaluator,
)
from app.evaluation.dataset import EvaluationDataset, GroundTruthCase, load_dataset
from app.evaluation.numerical_auditor import NumericalAccuracyEvaluator, NumericalAuditResult
from app.graph.workflow import get_compiled_graph
from app.tools.market_data import MarketDataClient, MarketQuote
from app.tools.sec import SECClient
from app.tools.web_search import WebSearchClient

ACCURACY_THRESHOLD = 0.95
CITATION_THRESHOLD = 0.95


class CaseScorecard(BaseModel):
    case_id: str
    ticker: str
    elapsed_seconds: float
    numerical: NumericalAuditResult
    citation: CitationAuditResult
    passed: bool


class EvaluationScorecard(BaseModel):
    passed: bool
    numerical_precision: float
    citation_provenance_rate: float
    mean_graph_execution_seconds: float
    hallucination_count: int
    cases: list[CaseScorecard] = Field(default_factory=list)


def _period_publication_date(period: str) -> str:
    match = re.search(r"(20\d{2})", period)
    year = match.group(1) if match else "2025"
    quarter = period.upper()
    if "Q4" in quarter:
        return f"{year}-09-28"
    if "Q3" in quarter:
        return f"{year}-08-27"
    if "Q2" in quarter:
        return f"{year}-05-28"
    if "Q1" in quarter:
        return f"{year}-02-26"
    return f"{year}-06-30"


@contextmanager
def offline_providers(cases: list[GroundTruthCase]) -> Iterator[None]:
    """Inject per-ticker SEC/Yahoo/web fixtures and restore the live clients afterwards."""
    by_ticker = {case.ticker.upper(): case for case in cases}
    originals = {
        "sec": SECClient.get_quarterly_financials,
        "news": WebSearchClient.search_company_news,
        "quote": MarketDataClient.fetch_quote,
    }

    async def _financials(self: SECClient, ticker: str, periods_count: int = 4):
        case = by_ticker.get(ticker.upper())
        if case is None:
            return []
        return [
            RawMetric(
                name=name,
                period=case.analysis_period,
                value=value,
                source_filing="10-Q",
            )
            for name, value in case.canonical_metrics.items()
        ]

    async def _news(self, ticker: str, query: str, max_results: int = 3):
        case = by_ticker.get(ticker.upper())
        facts = case.known_facts if case else []
        published = _period_publication_date(case.analysis_period) if case else "2025-08-01"
        return [
            {
                "title": f"{ticker} qualitative context",
                "url": "https://example.com/eval",
                "snippet": facts[0] if facts else f"{ticker} evaluation fixture.",
                "published_date": published,
            }
        ]

    async def _quote(self, ticker: str) -> MarketQuote:
        return MarketQuote(
            ticker=ticker,
            regular_market_price=1.0,
            regular_market_volume=1_000_000.0,
            market_cap=1_000_000_000.0,
            trailing_pe=20.0,
        )

    SECClient.get_quarterly_financials = _financials  # type: ignore[method-assign]
    WebSearchClient.search_company_news = _news  # type: ignore[method-assign]
    MarketDataClient.fetch_quote = _quote  # type: ignore[method-assign]
    try:
        yield
    finally:
        SECClient.get_quarterly_financials = originals["sec"]  # type: ignore[method-assign]
        WebSearchClient.search_company_news = originals["news"]  # type: ignore[method-assign]
        MarketDataClient.fetch_quote = originals["quote"]  # type: ignore[method-assign]


async def _run_case(case: GroundTruthCase, graph: Any) -> tuple[ResearchReport, float]:
    started = time.perf_counter()
    result = await graph.ainvoke(
        {
            "user_query": case.query,
            "run_id": f"eval-{case.case_id}-{uuid4().hex[:8]}",
            "iteration_count": 0,
            "max_iterations": 2,
            "is_validated": False,
        },
        {"configurable": {"thread_id": f"eval-{case.case_id}-{uuid4().hex[:8]}"}},
    )
    elapsed = time.perf_counter() - started
    raw = result.get("final_report") if isinstance(result, dict) else None
    if isinstance(raw, ResearchReport):
        return raw, elapsed
    if raw is None:
        raise RuntimeError(f"Evaluation graph produced no report for {case.case_id}")
    return ResearchReport.model_validate(raw), elapsed


async def evaluate_dataset(
    dataset: EvaluationDataset | None = None,
    graph: Any | None = None,
    offline: bool = True,
) -> EvaluationScorecard:
    bundle = dataset or load_dataset()
    compiled = graph or get_compiled_graph()
    numerical = NumericalAccuracyEvaluator()
    citation = CitationFaithfulnessEvaluator()

    async def _score_cases() -> list[CaseScorecard]:
        rows: list[CaseScorecard] = []
        for case in bundle.cases:
            report, elapsed = await _run_case(case, compiled)
            num = numerical.evaluate(report, case)
            cite = await citation.evaluate_with_optional_judge(report)
            rows.append(
                CaseScorecard(
                    case_id=case.case_id,
                    ticker=case.ticker,
                    elapsed_seconds=elapsed,
                    numerical=num,
                    citation=cite,
                    passed=num.metric_accuracy_score >= ACCURACY_THRESHOLD
                    and cite.citation_coverage >= CITATION_THRESHOLD
                    and not num.phantom_metrics,
                )
            )
        return rows

    if offline:
        with offline_providers(bundle.cases):
            rows = await _score_cases()
    else:
        rows = await _score_cases()

    precision = sum(row.numerical.metric_accuracy_score for row in rows) / (len(rows) or 1)
    provenance = sum(row.citation.citation_coverage for row in rows) / (len(rows) or 1)
    mean_time = sum(row.elapsed_seconds for row in rows) / (len(rows) or 1)
    hallucinations = sum(len(row.numerical.phantom_metrics) for row in rows)
    passed = (
        all(row.passed for row in rows)
        and precision >= ACCURACY_THRESHOLD
        and provenance >= CITATION_THRESHOLD
    )
    return EvaluationScorecard(
        passed=passed,
        numerical_precision=precision,
        citation_provenance_rate=provenance,
        mean_graph_execution_seconds=mean_time,
        hallucination_count=hallucinations,
        cases=rows,
    )


def render_scorecard(scorecard: EvaluationScorecard) -> str:
    status = "PASS" if scorecard.passed else "FAIL"
    lines = [
        "# Evaluation Scorecard",
        "",
        f"- **Overall status:** {status}",
        f"- **Numerical precision:** {scorecard.numerical_precision:.2%}",
        f"- **Citation provenance rate:** {scorecard.citation_provenance_rate:.2%}",
        f"- **Mean graph execution time:** {scorecard.mean_graph_execution_seconds:.2f}s",
        f"- **Hallucination / phantom metric count:** {scorecard.hallucination_count}",
        "",
        "| Case | Ticker | Accuracy | Citations | Time (s) | Result |",
        "|---|---|---|---|---|---|",
    ]
    for row in scorecard.cases:
        lines.append(
            f"| {row.case_id} | {row.ticker} | {row.numerical.metric_accuracy_score:.2%} | "
            f"{row.citation.citation_coverage:.2%} | {row.elapsed_seconds:.2f} | "
            f"{'PASS' if row.passed else 'FAIL'} |"
        )
    if any(row.numerical.mismatches for row in scorecard.cases):
        lines.extend(["", "## Mismatches"])
        for row in scorecard.cases:
            for item in row.numerical.mismatches:
                lines.append(f"- `{row.case_id}` {item}")
    return "\n".join(lines) + "\n"


def write_scorecard(scorecard: EvaluationScorecard, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_scorecard(scorecard), encoding="utf-8")
    return target
