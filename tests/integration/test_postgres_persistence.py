import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.api.schemas.reports import ResearchReport, ValidationResult
from app.memory.long_term import PostgresResearchMemoryStore
from app.persistence.database import dispose_engine, get_engine, sqlalchemy_url
from app.persistence.models import Base
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.schemas import DocumentChunk, DocumentMetadata
from app.rag.store import PgVectorStore

DEFAULT_DSN = "postgresql+asyncpg://postgres:postgres@localhost:5432/quant_research"


async def _postgres_reachable(dsn: str) -> bool:
    engine = None
    try:
        engine = get_engine(dsn)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await dispose_engine()


@pytest.fixture
async def postgres_dsn():
    dsn = sqlalchemy_url(os.getenv("DATABASE_URL") or DEFAULT_DSN)
    if dsn is None or not await _postgres_reachable(dsn):
        pytest.skip("Postgres not available")
    os.environ["DATABASE_URL"] = dsn
    engine = get_engine(dsn)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield dsn
    await dispose_engine()


def _sample_report(run_id: str, ticker: str = "NVDA") -> ResearchReport:
    return ResearchReport(
        run_id=run_id,
        company_name="NVIDIA Corporation",
        ticker=ticker,
        analysis_period="Q3-2025",
        generated_at=datetime.now(timezone.utc),
        executive_conclusion="Data-center mix remains the primary earnings driver.",
        key_findings=["Gross margin expanded on Hopper/Blackwell mix."],
        bull_case=["Sustained accelerator demand."],
        bear_case=["Customer concentration risk."],
        risk_factors=["Export controls."],
        financial_metrics={"Revenue": 35_082_000_000.0},
        derived_metrics={},
        validation_audit=ValidationResult(
            is_valid=True,
            deterministic_passed=True,
            semantic_passed=True,
        ),
        aggregate_confidence_score=0.9,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pgvector_inserts_and_retrieves_with_temporal_filter(postgres_dsn):
    store = PgVectorStore(dsn=postgres_dsn, embedder=HashEmbeddingProvider())
    ticker = f"T{uuid4().hex[:6].upper()}"
    current = DocumentChunk(
        chunk_id=str(uuid4()),
        content="Q3-2025 10-Q: services revenue accelerated and gross margin expanded.",
        metadata=DocumentMetadata(
            ticker=ticker,
            company_name="Test Corp",
            document_type="10-Q",
            financial_period="Q3-2025",
            publication_date="2025-08-01",
        ),
    )
    stale = DocumentChunk(
        chunk_id=str(uuid4()),
        content="Q1-2022 10-Q: supply constraints weighed on units and inventory.",
        metadata=DocumentMetadata(
            ticker=ticker,
            company_name="Test Corp",
            document_type="10-Q",
            financial_period="Q1-2022",
            publication_date="2022-04-28",
        ),
    )
    await store.add_documents([current, stale])

    results = await store.similarity_search(
        query="services revenue gross margin",
        ticker=ticker,
        period="Q3-2025",
        top_k=2,
    )

    assert results
    assert results[0].metadata.ticker == ticker
    assert results[0].metadata.financial_period == "Q3-2025"
    assert results[0].temporal_warning is None
    stale_hits = [chunk for chunk in results if chunk.metadata.financial_period != "Q3-2025"]
    assert all(chunk.temporal_warning for chunk in stale_hits)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_research_memory_saves_and_loads_report(postgres_dsn):
    store = PostgresResearchMemoryStore()
    run_id = f"run-{uuid4()}"
    report = _sample_report(run_id, ticker="NVDA")

    await store.save_report(report)
    retrieved = await store.get_latest_reports("NVDA", limit=5)

    assert retrieved
    match = next(item for item in retrieved if item.run_id == run_id)
    assert match.ticker == "NVDA"
    assert match.analysis_period == "Q3-2025"
    assert match.executive_conclusion == report.executive_conclusion
    assert match.financial_metrics["Revenue"] == 35_082_000_000.0
