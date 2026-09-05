from typing import List, Optional

from app.rag.chunking import chunk_document
from app.rag.embeddings import BaseEmbeddingProvider, get_embedding_provider
from app.rag.schemas import DocumentChunk, DocumentMetadata
from app.rag.store import VectorStore, create_vector_store

RAG_SOURCE = "Internal RAG / Filings Archive"


class RAGRetrieverTool:
    """Reusable retrieval facade over the temporal vector store."""

    def __init__(
        self,
        store: Optional[VectorStore] = None,
        embedder: Optional[BaseEmbeddingProvider] = None,
    ) -> None:
        self.embedder = embedder or get_embedding_provider()
        self.store = store or create_vector_store(self.embedder)

    async def ingest(self, text: str, metadata: DocumentMetadata) -> List[DocumentChunk]:
        chunks = chunk_document(text, metadata)
        await self.store.add_documents(chunks)
        return chunks

    async def search(
        self,
        query: str,
        ticker: str,
        period: Optional[str] = None,
        top_k: int = 3,
    ) -> List[DocumentChunk]:
        return await self.store.similarity_search(
            query=query, ticker=ticker, period=period, top_k=top_k
        )


_default_tool: Optional[RAGRetrieverTool] = None


def get_rag_tool() -> RAGRetrieverTool:
    global _default_tool
    if _default_tool is None:
        _default_tool = RAGRetrieverTool()
    return _default_tool


def set_rag_tool(tool: Optional[RAGRetrieverTool]) -> None:
    global _default_tool
    _default_tool = tool
