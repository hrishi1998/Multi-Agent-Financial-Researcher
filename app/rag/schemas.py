from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    ticker: str
    company_name: str
    document_type: str  # "10-K", "10-Q", "earnings_call"
    financial_period: str  # "Q3-2025"
    publication_date: str


class DocumentChunk(BaseModel):
    chunk_id: str
    content: str
    metadata: DocumentMetadata
    embedding: Optional[List[float]] = None
    temporal_warning: Optional[str] = Field(
        default=None,
        description="Set when the chunk period does not match the requested period.",
    )
