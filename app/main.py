from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.research import router as research_router
from app.services.run_manager import run_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.run_manager = run_manager
    yield


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
app.include_router(research_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
