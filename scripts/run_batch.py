"""Offline batch research: invoke the graph per ticker and write Markdown reports.

Run with LLM_PROVIDER=mock to keep the job off live OpenAI/Anthropic/SEC calls.
This script does not start Redis SSE streaming.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.batch_service import (  # noqa: E402
    DEFAULT_QUERY_TEMPLATE,
    BatchResearchManager,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline batch financial research.")
    parser.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated ticker list, e.g. AAPL,MSFT,NVDA",
    )
    parser.add_argument("--output-dir", default="./outputs", help="Directory for Markdown reports")
    parser.add_argument(
        "--query-template",
        default=DEFAULT_QUERY_TEMPLATE,
        help="Query template; use {ticker} as the placeholder",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max simultaneous graph runs (asyncio.Semaphore)",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    tickers = [part.strip() for part in args.tickers.split(",") if part.strip()]
    if not tickers:
        logging.error("No tickers provided.")
        return 2
    logging.info(
        "Starting batch for %s tickers (concurrency=%s, LLM_PROVIDER=%s)",
        len(tickers),
        args.concurrency,
        os.getenv("LLM_PROVIDER", "openai"),
    )
    manager = BatchResearchManager(concurrency=args.concurrency)
    summary = await manager.execute_batch(
        tickers=tickers,
        query_template=args.query_template,
        output_dir=args.output_dir,
    )
    logging.info(
        "Batch %s finished: %s/%s succeeded, %s failed",
        summary.batch_id,
        summary.succeeded,
        summary.total,
        summary.failed,
    )
    for path in summary.output_files:
        logging.info("  wrote %s", path)
    for error in summary.errors:
        logging.error("  %s", error)
    return 0 if summary.failed == 0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run(parse_args())))


if __name__ == "__main__":
    main()
