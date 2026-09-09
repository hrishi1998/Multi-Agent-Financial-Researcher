import asyncio
import logging
from typing import Any, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.api.schemas.reports import ResearchReport
from app.graph.workflow import get_compiled_graph
from app.services.exporter import ReportExporter

logger = logging.getLogger(__name__)

DEFAULT_QUERY_TEMPLATE = (
    "Evaluate the financial performance of {ticker} over the last 4 quarters"
)
DEFAULT_CONCURRENCY = 5


class BatchSummary(BaseModel):
    batch_id: str
    total: int
    succeeded: int
    failed: int
    errors: List[str] = Field(default_factory=list)
    output_files: List[str] = Field(default_factory=list)


class BatchResearchManager:
    """Offline fan-out over tickers with a hard concurrency cap. No SSE / Redis."""

    def __init__(
        self,
        concurrency: int = DEFAULT_CONCURRENCY,
        graph: Any | None = None,
        exporter: ReportExporter | None = None,
    ) -> None:
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.concurrency = max(1, concurrency)
        self._graph = graph
        self.exporter = exporter or ReportExporter()
        self.in_flight = 0
        self.max_in_flight = 0

    def _compiled_graph(self) -> Any:
        return self._graph or get_compiled_graph()

    def _query(self, ticker: str, query_template: str) -> str:
        try:
            return query_template.format(ticker=ticker)
        except (KeyError, ValueError):
            return f"{query_template} {ticker}"

    async def execute_batch(
        self,
        tickers: List[str],
        query_template: str = DEFAULT_QUERY_TEMPLATE,
        output_dir: str = "outputs/",
        batch_id: Optional[str] = None,
    ) -> BatchSummary:
        job_id = batch_id or str(uuid4())
        unique = [ticker.strip().upper() for ticker in tickers if ticker and ticker.strip()]
        tasks = [
            asyncio.create_task(
                self._run_ticker(job_id, ticker, query_template, output_dir)
            )
            for ticker in unique
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        succeeded = 0
        failed = 0
        errors: List[str] = []
        output_files: List[str] = []
        for ticker, result in zip(unique, results, strict=True):
            if isinstance(result, Exception):
                failed += 1
                errors.append(f"{ticker}: {result}")
                logger.exception("Batch ticker %s failed", ticker, exc_info=result)
                continue
            if isinstance(result, str):
                succeeded += 1
                output_files.append(result)
            else:
                failed += 1
                errors.append(f"{ticker}: missing report artifact")

        return BatchSummary(
            batch_id=job_id,
            total=len(unique),
            succeeded=succeeded,
            failed=failed,
            errors=errors,
            output_files=output_files,
        )

    async def _run_ticker(
        self,
        batch_id: str,
        ticker: str,
        query_template: str,
        output_dir: str,
    ) -> str:
        async with self.semaphore:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                report = await self._invoke_graph(batch_id, ticker, query_template)
                path = await self.exporter.export_to_disk(report, output_dir=output_dir)
                logger.info("Exported %s report to %s", ticker, path)
                return str(path)
            finally:
                self.in_flight -= 1

    async def _invoke_graph(
        self,
        batch_id: str,
        ticker: str,
        query_template: str,
    ) -> ResearchReport:
        graph = self._compiled_graph()
        run_id = f"batch-{batch_id}-{ticker}"
        inputs = {
            "user_query": self._query(ticker, query_template),
            "run_id": run_id,
            "iteration_count": 0,
            "max_iterations": 2,
            "is_validated": False,
        }
        config = {
            "configurable": {"thread_id": run_id},
            "run_name": "Financial_Research_Batch",
            "metadata": {"ticker": ticker, "batch_id": batch_id},
            "tags": ["financial-research", "batch"],
        }
        result = await graph.ainvoke(inputs, config)
        report = self._extract_report(result)
        if report is None and hasattr(graph, "aget_state"):
            snapshot = await graph.aget_state(config)
            if snapshot and snapshot.next:
                result = await graph.ainvoke(None, config)
                report = self._extract_report(result)
        if report is None:
            raise RuntimeError(f"Graph completed without a ResearchReport for {ticker}")
        return report

    def _extract_report(self, result: Any) -> ResearchReport | None:
        raw = result.get("final_report") if isinstance(result, dict) else None
        if raw is None:
            return None
        if isinstance(raw, ResearchReport):
            return raw
        return ResearchReport.model_validate(raw)
