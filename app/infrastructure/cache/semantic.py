import os
from typing import List, Optional, Tuple

from app.api.schemas.reports import ResearchReport
from app.rag.embeddings import BaseEmbeddingProvider, get_embedding_provider

COSINE_THRESHOLD = 0.95


def semantic_cache_enabled() -> bool:
    if os.getenv("ENABLE_SEMANTIC_CACHE") == "1":
        return True
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return bool(os.getenv("DATABASE_URL"))


def _cosine(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


class InMemorySemanticCacheStore:
    def __init__(self, embedder: Optional[BaseEmbeddingProvider] = None) -> None:
        self.embedder = embedder or get_embedding_provider()
        self._entries: List[Tuple[str, List[float], ResearchReport]] = []

    async def lookup(self, query: str) -> Optional[ResearchReport]:
        query_vec = await self.embedder.embed_text(query)
        best: Optional[ResearchReport] = None
        best_score = -1.0
        for _text, embedding, report in self._entries:
            score = _cosine(query_vec, embedding)
            if score > best_score:
                best_score = score
                best = report
        if best is not None and best_score > COSINE_THRESHOLD:
            return ResearchReport.model_validate(best.model_dump(mode="json"))
        return None

    async def save(self, query: str, report: ResearchReport) -> None:
        embedding = await self.embedder.embed_text(query)
        self._entries.append((query, embedding, report))


class PostgresSemanticCacheStore:
    def __init__(self, embedder: Optional[BaseEmbeddingProvider] = None) -> None:
        self.embedder = embedder or get_embedding_provider()

    async def lookup(self, query: str) -> Optional[ResearchReport]:
        from sqlalchemy import select

        from app.persistence.database import get_session_factory
        from app.persistence.models import CachedQueryTable

        query_vec = await self.embedder.embed_text(query)
        distance = CachedQueryTable.query_embedding.cosine_distance(query_vec)
        stmt = (
            select(CachedQueryTable, distance.label("distance"))
            .order_by(distance)
            .limit(1)
        )
        async with get_session_factory()() as session:
            row = (await session.execute(stmt)).first()
        if row is None:
            return None
        cached, dist = row
        similarity = 1.0 - float(dist)
        if similarity <= COSINE_THRESHOLD:
            return None
        return ResearchReport.model_validate(cached.report_json)

    async def save(self, query: str, report: ResearchReport) -> None:
        from app.persistence.database import get_session_factory
        from app.persistence.models import CachedQueryTable

        embedding = await self.embedder.embed_text(query)
        async with get_session_factory()() as session:
            session.add(
                CachedQueryTable(
                    query_text=query,
                    query_embedding=embedding,
                    report_json=report.model_dump(mode="json"),
                )
            )
            await session.commit()


class SemanticCacheStore:
    def __init__(self, embedder: Optional[BaseEmbeddingProvider] = None) -> None:
        from app.persistence.database import use_postgres_persistence

        if use_postgres_persistence():
            self._backend = PostgresSemanticCacheStore(embedder=embedder)
        else:
            self._backend = InMemorySemanticCacheStore(embedder=embedder)

    async def lookup(self, query: str) -> Optional[ResearchReport]:
        return await self._backend.lookup(query)

    async def save(self, query: str, report: ResearchReport) -> None:
        await self._backend.save(query, report)


_store: Optional[SemanticCacheStore] = None


def get_semantic_cache() -> SemanticCacheStore:
    global _store
    if _store is None:
        _store = SemanticCacheStore()
    return _store
