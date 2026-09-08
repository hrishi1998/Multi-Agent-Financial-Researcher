import asyncio
import os

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.persistence.database import sqlalchemy_url

router = APIRouter(tags=["health"])


def _configured_llm_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "openai").strip().lower()


async def _database_status() -> str:
    url = sqlalchemy_url()
    if not url:
        return "not_configured"
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "disconnected"
    finally:
        await engine.dispose()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "database": await _database_status(),
        "llm_provider": _configured_llm_provider(),
    }
