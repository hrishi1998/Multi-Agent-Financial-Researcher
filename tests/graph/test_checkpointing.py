import pytest

from app.graph.workflow import graph


@pytest.mark.asyncio
async def test_memory_saver_persists_formatted_report():
    config = {"configurable": {"thread_id": "test_thread_001"}}
    await graph.ainvoke({"user_query": "Test Checkpointing NVDA"}, config)

    persisted_state = graph.get_state(config)
    final_report = persisted_state.values["final_report"]

    assert final_report is not None
    ticker = final_report.ticker if hasattr(final_report, "ticker") else final_report["ticker"]
    company = (
        final_report.company_name
        if hasattr(final_report, "company_name")
        else final_report["company_name"]
    )
    assert ticker == "NVDA"
    assert company == "NVIDIA Corporation"
    assert persisted_state.values["execution_trace"][-1]["node"] == "formatter"
    assert persisted_state.values["execution_trace"][-1]["status"] == "completed"
