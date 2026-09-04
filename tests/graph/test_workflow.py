import time

import pytest

from app.graph.workflow import graph


@pytest.mark.asyncio
async def test_compiled_graph_fans_out_and_aggregates_evidence():
    started = time.perf_counter()
    result = await graph.ainvoke({"user_query": "Analyze NVDA Q3-2025"})
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert len(result["evidence"]) == 5
    assert {item.source for item in result["evidence"]} == {
        "SEC EDGAR",
        "Yahoo Finance",
        "Reuters",
        "Internal Research Memo",
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
        "synthesizer",
    }
    assert all(entry["status"] == "completed" for entry in result["execution_trace"])
    assert result["plan"].ticker == "NVDA"
    assert result["user_query"] == "Analyze NVDA Q3-2025"

    final_report = result["final_report"]
    assert final_report is not None
    assert final_report["evidence_count"] == 5
    assert final_report["ticker"] == "NVDA"
    assert final_report["by_source"] == {
        "SEC EDGAR": 2,
        "Yahoo Finance": 1,
        "Reuters": 1,
        "Internal Research Memo": 1,
    }
    assert "5 evidence items" in final_report["summary"]
