from typing import List

from app.api.schemas.reports import Evidence, SourceType


def missing_source_warnings(evidence: List[Evidence]) -> List[str]:
    """Document researcher dropouts for validators and the final report."""
    types = {item.source_type for item in evidence}
    warnings: List[str] = []
    if SourceType.FILING not in types:
        warnings.append("Missing SEC filings: financial researcher returned no evidence.")
    if SourceType.MARKET_API not in types:
        warnings.append("Missing market data: quote provider failed or timed out.")
    if SourceType.NEWS not in types:
        warnings.append("Missing web/news evidence: search provider failed or returned no results.")
    return warnings
