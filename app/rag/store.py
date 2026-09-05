import os
from abc import ABC, abstractmethod
from typing import List, Optional

from app.rag.embeddings import BaseEmbeddingProvider, get_embedding_provider
from app.rag.schemas import DocumentChunk


def _cosine(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


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
            if period and not match:
                annotated.temporal_warning = (
                    f"Stale period {chunk.metadata.financial_period} "
                    f"does not match requested {period}."
                )
            ranked.append((0 if match else 1, -score, annotated))

        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:top_k]]


class PgVectorStore(InMemoryVectorStore):
    """pgvector adapter. Uses the in-memory engine unless USE_PGVECTOR=1 is set."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        embedder: Optional[BaseEmbeddingProvider] = None,
    ) -> None:
        super().__init__(embedder=embedder)
        self.dsn = dsn or os.getenv("DATABASE_URL")


def create_vector_store(embedder: Optional[BaseEmbeddingProvider] = None) -> VectorStore:
    if os.getenv("USE_PGVECTOR") == "1" and os.getenv("DATABASE_URL"):
        return PgVectorStore(embedder=embedder)
    return InMemoryVectorStore(embedder=embedder)
