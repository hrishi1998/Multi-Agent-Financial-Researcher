"""Provision Postgres tables and the pgvector extension."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.persistence.database import dispose_engine, get_engine, sqlalchemy_url  # noqa: E402
from app.persistence.models import Base  # noqa: E402


async def setup_database(dsn: str | None = None) -> None:
    url = sqlalchemy_url(dsn)
    if not url:
        raise RuntimeError("DATABASE_URL is required to provision the research database.")
    engine = get_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    await dispose_engine()


def main() -> None:
    asyncio.run(setup_database(os.getenv("DATABASE_URL")))


if __name__ == "__main__":
    main()
