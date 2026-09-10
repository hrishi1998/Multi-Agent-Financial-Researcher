import os
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from app.rag.embeddings import BaseEmbeddingProvider, get_embedding_provider
from app.rag.schemas import DocumentChunk, DocumentMetadata


def _cosine(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _temporal_warning(chunk_period: str, requested: Optional[str]) -> Optional[str]:
    if requested and chunk_period != requested:
        return f"Stale period {chunk_period} does not match requested {requested}."
    return None


class VectorStore(ABC):
    @abstractmethod
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def similarity_search(
        self,
        query: str,
        ticker: str,
        period: Optional[str] = None,
        top_k: int = 3,
    ) -> List[DocumentChunk]:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """Local cosine store with strict ticker filtering and period prioritization."""

    def __init__(self, embedder: Optional[BaseEmbeddingProvider] = None) -> None:
        self.embedder = embedder or get_embedding_provider()
        self._chunks: List[DocumentChunk] = []

    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        for chunk in chunks:
            if chunk.embedding is None:
                chunk.embedding = await self.embedder.embed_text(chunk.content)
            self._chunks.append(chunk)

    async def similarity_search(
        self,
        query: str,
        ticker: str,
        period: Optional[str] = None,
        top_k: int = 3,
    ) -> List[DocumentChunk]:
        query_vec = await self.embedder.embed_text(query)
        ticker_key = ticker.upper().strip()
        ranked: List[tuple[int, float, DocumentChunk]] = []

        for chunk in self._chunks:
            if chunk.metadata.ticker.upper() != ticker_key:
                continue
            if not chunk.embedding:
                continue
            score = _cosine(query_vec, chunk.embedding)
            match = period is None or chunk.metadata.financial_period == period
            annotated = chunk.model_copy(deep=True)
            annotated.temporal_warning = _temporal_warning(chunk.metadata.financial_period, period)
            ranked.append((0 if match else 1, -score, annotated))

        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:top_k]]


class PgVectorStore(VectorStore):
    """PostgreSQL + pgvector store with ticker filters and period-first ranking."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        embedder: Optional[BaseEmbeddingProvider] = None,
    ) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self.embedder = embedder or get_embedding_provider()

    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        from app.persistence.database import get_session_factory
        from app.persistence.models import DocumentChunkTable

        if not chunks:
            return
        rows = []
        for chunk in chunks:
            embedding = chunk.embedding
            if embedding is None:
                embedding = await self.embedder.embed_text(chunk.content)
                chunk.embedding = embedding
            rows.append(
                DocumentChunkTable(
                    id=chunk.chunk_id,
                    ticker=chunk.metadata.ticker.upper(),
                    company_name=chunk.metadata.company_name,
                    document_type=chunk.metadata.document_type,
                    financial_period=chunk.metadata.financial_period,
                    publication_date=chunk.metadata.publication_date,
                    content=chunk.content,
                    embedding=embedding,
                )
            )
        async with get_session_factory(self.dsn)() as session:
            session.add_all(rows)
            await session.commit()

    async def similarity_search(
        self,
        query: str,
        ticker: str,
        period: Optional[str] = None,
        top_k: int = 3,
    ) -> List[DocumentChunk]:
        from sqlalchemy import case, select

        from app.persistence.database import get_session_factory
        from app.persistence.models import DocumentChunkTable

        query_vec = await self.embedder.embed_text(query)
        ticker_key = ticker.upper().strip()
        distance = DocumentChunkTable.embedding.l2_distance(query_vec)
        stmt = select(DocumentChunkTable).where(DocumentChunkTable.ticker == ticker_key)
        if period:
            period_rank = case(
                (DocumentChunkTable.financial_period == period, 0),
                else_=1,
            )
            stmt = stmt.order_by(period_rank, distance)
        else:
            stmt = stmt.order_by(distance)
        stmt = stmt.limit(top_k)
        async with get_session_factory(self.dsn)() as session:
            rows: Sequence[DocumentChunkTable] = (await session.scalars(stmt)).all()
        return [_row_to_chunk(row, period) for row in rows]


def _row_to_chunk(row, period: Optional[str]) -> DocumentChunk:
    embedding = None
    if row.embedding is not None:
        embedding = [float(value) for value in list(row.embedding)]
    return DocumentChunk(
        chunk_id=str(row.id),
        content=row.content,
        metadata=DocumentMetadata(
            ticker=row.ticker,
            company_name=row.company_name,
            document_type=row.document_type,
            financial_period=row.financial_period,
            publication_date=row.publication_date,
        ),
        embedding=embedding,
        temporal_warning=_temporal_warning(row.financial_period, period),
    )


def create_vector_store(embedder: Optional[BaseEmbeddingProvider] = None) -> VectorStore:
    from app.persistence.database import use_postgres_persistence

    if use_postgres_persistence():
        return PgVectorStore(embedder=embedder)
    return InMemoryVectorStore(embedder=embedder)
