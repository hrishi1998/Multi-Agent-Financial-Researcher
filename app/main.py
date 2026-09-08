import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.research import router as research_router
from app.graph.workflow import rebuild_graph
from app.infrastructure.observability.telemetry import configure_langsmith
from app.memory.short_term import setup_checkpointer, teardown_checkpointer
from app.persistence.database import dispose_engine
from app.services.run_manager import run_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup_checkpointer()
    rebuild_graph()
    app.state.run_manager = run_manager
    yield
    await teardown_checkpointer()
    await dispose_engine()


configure_langsmith()

app = FastAPI(
    title="Async Multi-Agent Quantitative Research Analyst",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(research_router, prefix="/api/v1")

if os.getenv("ENABLE_TELEMETRY") == "1":
    from app.infrastructure.observability.telemetry import setup_telemetry

    setup_telemetry(app)
