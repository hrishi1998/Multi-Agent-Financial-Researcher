import asyncio
import os
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver

from app.persistence.database import psycopg_url

_checkpointer: Any = None
_postgres_cm: Any = None


def get_checkpointer(postgres_uri: Optional[str] = None) -> Any:
    """Return the active checkpointer. MemorySaver unless Postgres was set up."""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    _ = postgres_uri or psycopg_url() or os.getenv("DATABASE_URL")
    _checkpointer = MemorySaver()
    return _checkpointer


async def setup_checkpointer(postgres_uri: Optional[str] = None) -> Any:
    """Open AsyncPostgresSaver when DATABASE_URL is set; otherwise MemorySaver."""
    global _checkpointer, _postgres_cm
    uri = psycopg_url(postgres_uri)
    if not uri:
        _checkpointer = MemorySaver()
        return _checkpointer
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=uri,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        await asyncio.wait_for(pool.open(), timeout=5)
        saver = AsyncPostgresSaver(conn=pool)
        await saver.setup()
        _postgres_cm = pool
        _checkpointer = saver
        return saver
    except Exception:
        _postgres_cm = None
        _checkpointer = MemorySaver()
        return _checkpointer


async def teardown_checkpointer() -> None:
    global _checkpointer, _postgres_cm
    if _postgres_cm is not None:
        try:
            close = getattr(_postgres_cm, "close", None)
            if close is not None:
                await close()
            else:
                await _postgres_cm.__aexit__(None, None, None)
        except Exception:
            pass
    _postgres_cm = None
    _checkpointer = None
