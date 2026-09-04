import pytest

from app.graph.workflow import graph

RESEARCHER_NODES = {
    "financial_researcher",
    "market_researcher",
    "web_researcher",
    "rag_researcher",
}


@pytest.mark.asyncio
async def test_graph_loops_once_then_converges():
    result = await graph.ainvoke(
        {
            "user_query": "Analyze NVDA Q3-2025",
            "iteration_count": 0,
            "max_iterations": 2,
            "is_validated": False,
        },
        {"configurable": {"thread_id": "test_cyclic_001"}},
    )

    trace = result["execution_trace"]
    nodes = [entry["node"] for entry in trace]

    assert nodes[0] == "planner"
    assert set(nodes[1:5]) == RESEARCHER_NODES
    assert nodes[5] == "validator"
    assert trace[5]["status"] == "failed"

    assert nodes[6] == "planner"
    assert set(nodes[7:11]) == RESEARCHER_NODES
    assert nodes[11] == "validator"
    assert trace[11]["status"] == "passed"

    assert nodes[12] == "quant_analysis"
    assert trace[12]["status"] == "completed"
    assert nodes[13] == "synthesizer"
    assert trace[13]["status"] == "completed"
    assert nodes[14] == "formatter"
    assert trace[14]["status"] == "completed"
    assert len(nodes) == 15
    assert result["iteration_count"] == 2
    assert result["is_validated"] is True
