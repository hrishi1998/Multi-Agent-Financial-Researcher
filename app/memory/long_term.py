from collections import defaultdict
from typing import Dict, List, Optional

from app.api.schemas.reports import ResearchReport


class InMemoryResearchMemoryStore:
    def __init__(self) -> None:
        self._by_ticker: Dict[str, List[ResearchReport]] = defaultdict(list)

    async def save_report(self, report: ResearchReport) -> None:
        self._by_ticker[report.ticker.upper()].append(report)

    async def get_reports(self, ticker: str) -> List[ResearchReport]:
        return list(self._by_ticker.get(ticker.upper(), []))

    async def get_latest_reports(self, ticker: str, limit: int = 5) -> List[ResearchReport]:
        return list(reversed(await self.get_reports(ticker)))[:limit]

    async def latest(self, ticker: str) -> Optional[ResearchReport]:
        reports = await self.get_latest_reports(ticker, limit=1)
        return reports[0] if reports else None


class PostgresResearchMemoryStore:
    async def save_report(self, report: ResearchReport) -> None:
        from sqlalchemy import select

        from app.persistence.database import get_session_factory
        from app.persistence.models import ResearchReportTable

        payload = report.model_dump(mode="json")
        async with get_session_factory()() as session:
            existing = await session.scalar(
                select(ResearchReportTable).where(ResearchReportTable.run_id == report.run_id)
            )
            if existing:
                existing.ticker = report.ticker.upper()
                existing.analysis_period = report.analysis_period
                existing.report_json = payload
            else:
                session.add(
                    ResearchReportTable(
                        run_id=report.run_id,
                        ticker=report.ticker.upper(),
                        analysis_period=report.analysis_period,
                        report_json=payload,
                    )
                )
            await session.commit()

    async def get_latest_reports(self, ticker: str, limit: int = 5) -> List[ResearchReport]:
        from sqlalchemy import select

        from app.persistence.database import get_session_factory
        from app.persistence.models import ResearchReportTable

        async with get_session_factory()() as session:
            rows = (
                await session.scalars(
                    select(ResearchReportTable)
                    .where(ResearchReportTable.ticker == ticker.upper())
                    .order_by(ResearchReportTable.created_at.desc())
                    .limit(limit)
                )
            ).all()
        return [ResearchReport.model_validate(row.report_json) for row in rows]

    async def get_reports(self, ticker: str) -> List[ResearchReport]:
        return await self.get_latest_reports(ticker, limit=50)

    async def latest(self, ticker: str) -> Optional[ResearchReport]:
        reports = await self.get_latest_reports(ticker, limit=1)
        return reports[0] if reports else None


class ResearchMemoryStore:
    """Persists completed reports. Uses Postgres when DATABASE_URL is configured."""

    def __init__(self) -> None:
        from app.persistence.database import use_postgres_persistence

        self._backend = (
            PostgresResearchMemoryStore()
            if use_postgres_persistence()
            else InMemoryResearchMemoryStore()
        )

    async def save_report(self, report: ResearchReport) -> None:
        await self._backend.save_report(report)

    async def get_reports(self, ticker: str) -> List[ResearchReport]:
        return await self._backend.get_reports(ticker)

    async def get_latest_reports(self, ticker: str, limit: int = 5) -> List[ResearchReport]:
        return await self._backend.get_latest_reports(ticker, limit=limit)

    async def latest(self, ticker: str) -> Optional[ResearchReport]:
        return await self._backend.latest(ticker)


_store: Optional[ResearchMemoryStore] = None


def get_research_memory() -> ResearchMemoryStore:
    global _store
    if _store is None:
        _store = ResearchMemoryStore()
    return _store
