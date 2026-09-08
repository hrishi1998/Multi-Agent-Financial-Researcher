import pytest

from app.graph.workflow import rebuild_graph


@pytest.mark.asyncio
async def test_graph_pauses_before_synthesizer_and_resumes(monkeypatch):
    monkeypatch.setenv("ENABLE_HITL", "1")
    graph = rebuild_graph()
    try:
        config = {"configurable": {"thread_id": "hitl-thread-001"}}
        await graph.ainvoke(
            {
                "user_query": "Analyze NVDA Q3-2025",
                "run_id": "hitl-run-001",
                "iteration_count": 0,
                "max_iterations": 2,
                "is_validated": False,
            },
            config,
        )

        paused = await graph.aget_state(config)
        assert "synthesizer" in list(paused.next)
        assert paused.values.get("final_report") is None
        assert paused.values.get("evidence")

        await graph.ainvoke(None, config)
        finished = await graph.aget_state(config)
        assert list(finished.next) == []
        assert finished.values.get("final_report") is not None
        assert finished.values["final_report"].ticker == "NVDA"
    finally:
        monkeypatch.delenv("ENABLE_HITL", raising=False)
        rebuild_graph()
