# Async Multi-Agent Quantitative Research Analyst

An asynchronous quantitative research engine that accepts company valuation and performance questions, gathers SEC filings and market evidence concurrently, enforces deterministic validation, and synthesizes auditable investment-research reports while streaming execution progress via SSE.

## Key Architectural Principles

- **Deterministic Ground Truth:** Financial calculations (margins, YoY/QoQ growth, leverage ratios) are executed strictly in Python. LLMs are restricted to qualitative interpretation and synthesis.
- **Fan-Out / Fan-In Concurrency:** SEC EDGAR, market feeds, web research, and vector retrieval execute concurrently via LangGraph stateful orchestration.
- **Auditable Evidence Graph:** Every synthesis claim is mapped directly to a filing reference, timestamped metric, and confidence score.
- **Real-time Streaming:** Native Server-Sent Events (SSE) stream state transitions, validation warnings, and sub-agent progress to the client.

## Tech Stack

- **Framework:** FastAPI, LangGraph, Pydantic v2
- **Data & Persistence:** PostgreSQL (`pgvector`), Redis
- **Data Sources:** SEC EDGAR (XBRL / 10-K / 10-Q), Market Data APIs
- **Observability:** LangSmith, OpenTelemetry
