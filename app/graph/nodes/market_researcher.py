from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState
from app.tools.market_data import MarketDataClient, MarketQuote


def _quote_to_evidence(ticker: str, quote: MarketQuote) -> List[Evidence]:
    fields: List[Tuple[str, Optional[float], str]] = [
        ("Price", quote.regular_market_price, f"{ticker} last price was {{}} USD."),
        ("Volume", quote.regular_market_volume, f"{ticker} regular-market volume was {{}}."),
        ("MarketCap", quote.market_cap, f"{ticker} market cap was {{}} USD."),
        ("TrailingPE", quote.trailing_pe, f"{ticker} trailing P/E was {{}}."),
    ]
    evidence: List[Evidence] = []
    for metric, value, claim_template in fields:
        if value is None:
            continue
        evidence.append(
            Evidence(
                source="Yahoo Finance",
                source_type=SourceType.MARKET_API,
                metric=metric,
                value=value,
                claim=claim_template.format(value),
            )
        )
    return evidence


async def market_researcher_node(state: ResearchState) -> Dict[str, Any]:
    """Fetch Yahoo Finance quotes and normalize them to Evidence. Never crash the graph."""
    plan = state.get("plan")
    ticker = plan.ticker if plan else "AAPL"

    try:
        client = MarketDataClient()
        quote = await client.fetch_quote(ticker)
        evidence = _quote_to_evidence(ticker, quote)
        return {
            "evidence": evidence,
            "execution_trace": [
                {
                    "node": "market_researcher",
                    "status": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "items": len(evidence),
                }
            ],
        }
    except (httpx.HTTPError, Exception) as exc:
        return {
            "evidence": [],
            "execution_trace": [
                {
                    "node": "market_researcher",
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
