import asyncio
import operator
import time
from typing import Any, Dict, List

import pytest

from app.api.schemas.reports import Evidence
from app.graph.nodes.financial_researcher import financial_researcher_node
from app.graph.nodes.market_researcher import market_researcher_node
from app.graph.nodes.rag_researcher import rag_researcher_node
from app.graph.nodes.web_researcher import web_researcher_node
from app.graph.state import ResearchPlan, ResearchState

CONCURRENCY_UPPER_BOUND_SECONDS = 0.8
SERIAL_SLEEP_SUM_SECONDS = 1.6


def _mock_state() -> ResearchState:
    return {
        "run_id": "test-run-concurrency",
        "user_query": "How did NVDA perform in Q3 2025?",
        "plan": ResearchPlan(
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            periods_to_fetch=["Q3-2025"],
            required_raw_metrics=["Revenue", "GrossProfit"],
            target_questions=["How did NVDA perform in Q3 2025?"],
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
async def test_researcher_nodes_run_concurrently_and_merge_evidence():
    state = _mock_state()
    started = time.perf_counter()
    updates = await asyncio.gather(
        financial_researcher_node(state),
        market_researcher_node(state),
        web_researcher_node(state),
        rag_researcher_node(state),
    )
    elapsed = time.perf_counter() - started

    assert elapsed < CONCURRENCY_UPPER_BOUND_SECONDS
    assert elapsed < SERIAL_SLEEP_SUM_SECONDS

    merged_evidence: List[Evidence] = []
    merged_trace: List[Dict[str, Any]] = []
    for update in updates:
        merged_evidence = operator.add(merged_evidence, update["evidence"])
        merged_trace = operator.add(merged_trace, update["execution_trace"])

    sources = {item.source for item in merged_evidence}
    nodes = {entry["node"] for entry in merged_trace}

    assert len(merged_evidence) >= 4
    assert sources == {
        "SEC EDGAR",
        "Yahoo Finance",
        "Web / News",
        "Internal RAG / Filings Archive",
    }
    assert nodes == {
        "financial_researcher",
        "market_researcher",
        "web_researcher",
        "rag_researcher",
    }
