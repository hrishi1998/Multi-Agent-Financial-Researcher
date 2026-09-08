from app.api.schemas.reports import ResearchReport, ValidationResult
from app.infrastructure.cache.semantic import InMemorySemanticCacheStore
from app.rag.embeddings import HashEmbeddingProvider


def _report(run_id: str = "cache-run-1") -> ResearchReport:
    return ResearchReport(
        run_id=run_id,
        company_name="NVIDIA Corporation",
        ticker="NVDA",
        analysis_period="Q3-2025",
        executive_conclusion="Cached conclusion.",
        key_findings=["Cache hit returns the same schema."],
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
        aggregate_confidence_score=0.9,
    )


async def test_identical_query_is_a_semantic_cache_hit():
    store = InMemorySemanticCacheStore(embedder=HashEmbeddingProvider())
    original = _report()
    await store.save("Analyze NVDA Q3-2025", original)

    cached = await store.lookup("Analyze NVDA Q3-2025")
    assert cached is not None
    assert cached.model_dump(mode="json") == original.model_dump(mode="json")
    assert cached.ticker == "NVDA"
    assert cached.executive_conclusion == "Cached conclusion."


async def test_unrelated_query_is_a_cache_miss():
    store = InMemorySemanticCacheStore(embedder=HashEmbeddingProvider())
    await store.save("Analyze NVDA Q3-2025", _report())
    assert await store.lookup("completely different commodity weather query") is None
