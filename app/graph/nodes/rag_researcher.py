from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState
from app.rag.schemas import DocumentChunk
from app.tools.rag import RAG_SOURCE, RAGRetrieverTool, get_rag_tool


def _chunk_to_evidence(chunk: DocumentChunk) -> Evidence:
    period = chunk.metadata.financial_period
    claim = f"{chunk.metadata.document_type} excerpt for {chunk.metadata.ticker} {period}."
    if chunk.temporal_warning:
        claim = f"{chunk.temporal_warning} {claim}"
    return Evidence(
        source=RAG_SOURCE,
        source_type=SourceType.INTERNAL_DOCUMENT,
        reporting_period=period,
        temporal_anchor=period,
        raw_text=chunk.content,
        claim=claim,
        confidence=0.55 if chunk.temporal_warning else 0.85,
    )


async def rag_researcher_node(
    state: ResearchState,
    retriever: Optional[RAGRetrieverTool] = None,
) -> Dict[str, Any]:
    """Retrieve temporally filtered archival excerpts. Never crash the graph."""
    plan = state.get("plan")
    ticker = plan.ticker if plan else "UNKNOWN"
    period = plan.periods_to_fetch[0] if plan and plan.periods_to_fetch else None
    query = (
        f"{ticker} {period or ''} qualitative commentary earnings notes "
        "gross margin product mix filings"
    )

    try:
        tool = retriever or get_rag_tool()
        chunks = await tool.search(query=query, ticker=ticker, period=period, top_k=3)
        current = [chunk for chunk in chunks if not chunk.temporal_warning]
        evidence = [_chunk_to_evidence(chunk) for chunk in current]
        note = None if evidence else "no historical documents indexed"
        return {
            "evidence": evidence,
            "execution_trace": [
                {
                    "node": "rag_researcher",
                    "status": "completed",
                    "note": note,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "items": len(evidence),
                }
            ],
        }
    except Exception as exc:
        return {
            "evidence": [],
            "execution_trace": [
                {
                    "node": "rag_researcher",
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
