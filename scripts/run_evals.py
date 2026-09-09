"""Run the offline evaluation suite and emit an executive scorecard."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.dataset import load_dataset  # noqa: E402
from app.evaluation.runner import (  # noqa: E402
    ACCURACY_THRESHOLD,
    CITATION_THRESHOLD,
    evaluate_dataset,
    render_scorecard,
    write_scorecard,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the research graph against SEC ground truth."
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to dataset.json (defaults to tests/evaluation/ground_truth/dataset.json)",
    )
    parser.add_argument(
        "--output",
        default="outputs/evaluation_scorecard.md",
        help="Markdown scorecard path",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Do not inject fixture SEC/Yahoo stubs (uses live providers if configured)",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    if not args.live:
        os.environ["LLM_PROVIDER"] = "mock"
    dataset = load_dataset(args.dataset) if args.dataset else load_dataset()
    scorecard = await evaluate_dataset(dataset=dataset, offline=not args.live)
    markdown = render_scorecard(scorecard)
    print(markdown)
    write_scorecard(scorecard, args.output)
    print(f"Wrote {args.output}")
    ok = (
        scorecard.passed
        and scorecard.numerical_precision >= ACCURACY_THRESHOLD
        and scorecard.citation_provenance_rate >= CITATION_THRESHOLD
    )
    return 0 if ok else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run(parse_args())))


if __name__ == "__main__":
    main()
