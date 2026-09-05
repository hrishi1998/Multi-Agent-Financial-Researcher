import time

import pytest

from app.graph.workflow import graph


@pytest.mark.asyncio
async def test_compiled_graph_fans_out_and_aggregates_evidence():
    started = time.perf_counter()
    result = await graph.ainvoke(
        {
            "user_query": "Analyze NVDA Q3-2025",
            "iteration_count": 0,
            "max_iterations": 2,
        },
        {"configurable": {"thread_id": "test_workflow_001"}},
    )
    elapsed = time.perf_counter() - started

    # Two parallel researcher waves (~0.6s each), not serial node time.
    assert elapsed < 2.0
    assert len(result["evidence"]) >= 10
    assert {item.source for item in result["evidence"]} == {
        "SEC EDGAR",
        "Yahoo Finance",
        "Web / News",
        "Internal RAG / Filings Archive",
    }
    financial_metrics = {
        item.metric for item in result["evidence"] if item.source == "SEC EDGAR"
    }
    assert financial_metrics == {"Revenue", "GrossProfit"}

    completed_nodes = {entry["node"] for entry in result["execution_trace"]}
    assert completed_nodes == {
        "planner",
        "financial_researcher",
        "market_researcher",
        "web_researcher",
        "rag_researcher",
        "validator",
        "quant_analysis",
        "synthesizer",
        "formatter",
    }
    assert result["plan"].ticker == "NVDA"
    assert result["user_query"] == "Analyze NVDA Q3-2025"
    assert result["iteration_count"] == 2

    final_report = result["final_report"]
    assert final_report is not None
    assert final_report.ticker == "NVDA"
    assert final_report.company_name == "NVIDIA Corporation"
    assert final_report.analysis_period == "Q3-2025"
    assert "Mock_Margin" in result["calculated_metrics"]
    assert result["execution_trace"][-1]["node"] == "formatter"
