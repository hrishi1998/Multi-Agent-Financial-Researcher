from collections import defaultdict
from typing import Dict, List, Optional

from app.api.schemas.reports import ResearchReport


class ResearchMemoryStore:
    """Cross-run store of completed ResearchReport summaries, keyed by ticker."""

    def __init__(self) -> None:
        self._by_ticker: Dict[str, List[ResearchReport]] = defaultdict(list)

    async def save_report(self, report: ResearchReport) -> None:
        self._by_ticker[report.ticker.upper()].append(report)

    async def get_reports(self, ticker: str) -> List[ResearchReport]:
        return list(self._by_ticker.get(ticker.upper(), []))

    async def latest(self, ticker: str) -> Optional[ResearchReport]:
        reports = await self.get_reports(ticker)
        return reports[-1] if reports else None
