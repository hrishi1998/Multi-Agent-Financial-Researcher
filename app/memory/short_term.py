from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer(postgres_uri: Optional[str] = None) -> Any:
    """Return a LangGraph checkpointer. Postgres is optional; MemorySaver is default."""
    uri = postgres_uri
    if uri:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            return AsyncPostgresSaver.from_conn_string(uri)
        except ImportError:
            pass
    return MemorySaver()
