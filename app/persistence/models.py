from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.persistence.database import vector_dimensions


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


try:
    from pgvector.sqlalchemy import Vector

    _VECTOR = Vector(vector_dimensions())
except Exception:  # pragma: no cover - import-time fallback for offline tooling
    _VECTOR = Text()


class DocumentChunkTable(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(64))
    financial_period: Mapped[str] = mapped_column(String(32), index=True)
    publication_date: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(_VECTOR)


class ResearchReportTable(Base):
    __tablename__ = "research_reports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    analysis_period: Mapped[str] = mapped_column(String(32))
    report_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
