from datetime import datetime, timezone
from typing import Any, Dict, List

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState
from app.infrastructure.http.resilience import NonRetryableError
from app.tools.web_search import WebSearchClient


def _hits_to_evidence(ticker: str, hits: List[Dict[str, str]]) -> List[Evidence]:
    evidence: List[Evidence] = []
    for hit in hits:
        snippet = hit.get("snippet") or ""
        title = hit.get("title") or f"{ticker} news"
        if not snippet and not title:
            continue
        evidence.append(
            Evidence(
                source="Web / News",
                source_type=SourceType.NEWS,
                claim=title,
                raw_text=snippet or title,
                source_url=hit.get("url") or None,
                temporal_anchor=hit.get("published_date") or None,
                confidence=0.85,
            )
        )
    return evidence


async def web_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Fetch qualitative news snippets. Never crash the graph on provider failure."""
    plan = state.get("plan")
    ticker = plan.ticker if plan else "AAPL"
    company = plan.company_name if plan else ticker
    questions = " ".join(plan.target_questions) if plan and plan.target_questions else "earnings outlook"
    query = f"{company} {questions} profitability revenue growth"

    try:
        client = WebSearchClient()
        hits = await client.search_company_news(ticker, query, max_results=3)
        evidence = _hits_to_evidence(ticker, hits)
        return {
            "evidence": evidence,
            "execution_trace": [
                {
                    "node": "web_researcher",
                    "status": "completed" if evidence else "completed",
                    "note": None if evidence else "no web results",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "items": len(evidence),
                }
            ],
        }
    except (NonRetryableError, Exception) as exc:
        return {
            "evidence": [],
            "execution_trace": [
                {
                    "node": "web_researcher",
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
