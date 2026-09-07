from langgraph.checkpoint.memory import MemorySaver

from app.api.schemas.reports import ResearchReport, ValidationResult
from app.memory.long_term import ResearchMemoryStore
from app.memory.short_term import get_checkpointer
from app.rag.store import InMemoryVectorStore, create_vector_store


def test_checkpointer_falls_back_to_memory_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.memory import short_term

    short_term._checkpointer = None
    saver = get_checkpointer()
    assert isinstance(saver, MemorySaver)


def test_vector_store_factory_stays_in_memory_without_postgres(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("USE_PGVECTOR", raising=False)
    assert isinstance(create_vector_store(), InMemoryVectorStore)


async def test_research_memory_store_roundtrip_in_memory(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = ResearchMemoryStore()
    report = ResearchReport(
        run_id="run-memory-1",
        company_name="NVIDIA Corporation",
        ticker="NVDA",
        analysis_period="Q3-2025",
        executive_conclusion="In-memory archive.",
        key_findings=["Fallback path works."],
        bull_case=[],
        bear_case=[],
        risk_factors=[],
        financial_metrics={"Revenue": 1.0},
        derived_metrics={},
        validation_audit=ValidationResult(
            is_valid=True,
            deterministic_passed=True,
            semantic_passed=True,
        ),
        aggregate_confidence_score=0.8,
    )
    await store.save_report(report)
    latest = await store.get_latest_reports("NVDA", limit=1)
    assert latest[0].run_id == "run-memory-1"
    assert latest[0].executive_conclusion == "In-memory archive."
