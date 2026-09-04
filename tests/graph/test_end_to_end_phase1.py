import pytest

from app.api.schemas.reports import CalculatedMetric, ResearchReport
from app.graph.workflow import graph


@pytest.mark.asyncio
async def test_phase1_pipeline_emits_typed_research_report():
    result = await graph.ainvoke(
        {
            "user_query": "Analyze NVDA Q3-2025",
            "iteration_count": 0,
            "max_iterations": 2,
            "is_validated": False,
        },
        {"configurable": {"thread_id": "test_e2e_phase1_001"}},
    )

    assert isinstance(result["final_report"], ResearchReport)
    assert result["final_report"].ticker == "NVDA"
    assert result["calculated_metrics"]
    assert any(isinstance(metric, CalculatedMetric) for metric in result["calculated_metrics"].values())
    assert "Mock_Margin" in result["calculated_metrics"]
    assert result["final_report"].derived_metrics

    nodes = [entry["node"] for entry in result["execution_trace"]]
    completion_path = nodes[-4:]
    assert completion_path == ["validator", "quant_analysis", "synthesizer", "formatter"]
    assert result["execution_trace"][-4]["status"] == "passed"
