import os
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def sqlalchemy_url(dsn: Optional[str] = None) -> Optional[str]:
    url = dsn or os.getenv("DATABASE_URL")
    if not url:
        return None
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def psycopg_url(dsn: Optional[str] = None) -> Optional[str]:
    url = dsn or os.getenv("DATABASE_URL")
    if not url:
        return None
    return (
        url.replace("postgresql+asyncpg://", "postgresql://", 1)
        .replace("postgres+asyncpg://", "postgresql://", 1)
    )


def vector_dimensions() -> int:
    return int(os.getenv("VECTOR_DIM", "64"))


def use_postgres_persistence() -> bool:
    """Use Postgres when a DSN is present, except during offline pytest runs."""
    if not os.getenv("DATABASE_URL"):
        return False
    if os.getenv("USE_PGVECTOR") == "1":
        return True
    return os.getenv("PYTEST_CURRENT_TEST") is None


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(dsn: Optional[str] = None) -> AsyncEngine:
    global _engine
    url = sqlalchemy_url(dsn)
    if not url:
        raise RuntimeError("DATABASE_URL is required for the SQLAlchemy engine.")
    if _engine is None:
        _engine = create_async_engine(url, pool_pre_ping=True)
    return _engine


def get_session_factory(dsn: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(dsn), expire_on_commit=False)
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
