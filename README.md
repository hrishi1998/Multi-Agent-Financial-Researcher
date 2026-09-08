# Async Multi-Agent Quantitative Research Analyst

An asynchronous quantitative research engine that accepts company valuation and performance questions, gathers SEC filings and market evidence concurrently, enforces deterministic validation, and synthesizes auditable investment-research reports while streaming execution progress via SSE.

## Key Architectural Principles

- **Deterministic Ground Truth:** Financial calculations (margins, YoY/QoQ growth, leverage ratios) are executed strictly in Python. LLMs are restricted to qualitative interpretation and synthesis.
- **Fan-Out / Fan-In Concurrency:** SEC EDGAR, market feeds, web research, and vector retrieval execute concurrently via LangGraph stateful orchestration.
- **Auditable Evidence Graph:** Every synthesis claim is mapped directly to a filing reference, timestamped metric, and confidence score.
- **Real-time Streaming:** Native Server-Sent Events (SSE) stream state transitions, validation warnings, and sub-agent progress to the client.

## Architecture

The compiled LangGraph workflow is:

`planner → [financial | market | web | rag] → validator ↺ planner → quant_analysis → synthesizer → formatter`

- **Fan-out / fan-in.** After the planner emits a `ResearchPlan`, four researcher nodes run concurrently and merge typed `Evidence` into shared state via `operator.add`. The join happens at the validator.
- **Cyclic validation.** The validator runs deterministic checks first (required metrics, arithmetic, temporal consistency). If the audit fails and `iteration_count < max_iterations`, control returns to the planner with a retry directive. The loop is bounded so a bad plan cannot spin forever.
- **Deterministic math vs. LLM interpretation.** `quant_analysis` is the only place that computes margins and growth. Planner, validator (semantic pass), and synthesizer may call an LLM. Numbers in the final `ResearchReport` come from `calculated_metrics`, never from model arithmetic.
- **Persistence.** Thread state can checkpoint to Postgres (`AsyncPostgresSaver`). Document chunks use pgvector; completed reports are archived as JSONB. Local/CI runs fall back to in-memory stores when `DATABASE_URL` is unset.

## Tech Stack

- **Framework:** FastAPI, LangGraph, Pydantic v2
- **Data & Persistence:** PostgreSQL (`pgvector`), Redis
- **Data Sources:** SEC EDGAR (XBRL / 10-K / 10-Q), Market Data APIs
- **Observability:** LangSmith, OpenTelemetry
- **Load testing:** Locust (dev extra)

## Performance & Benchmarks

These targets describe *infrastructure* throughput: FastAPI request handling plus LangGraph orchestration under `LLM_PROVIDER=mock`. They are **not** measurements of OpenAI, Anthropic, SEC EDGAR, or Yahoo Finance latency. Live provider calls must stay disabled during the load run.

| Metric | Baseline |
|---|---|
| Concurrent Users | 50 |
| API Latency (Health) | < 10ms |
| Graph Orchestration Overhead | [To be measured] |
| Failure Rate | 0% |

`Graph Orchestration Overhead` is the Locust custom event `Full Research Lifecycle`: wall time from `POST /api/v1/research` until `GET /api/v1/research/{run_id}` reports `completed` or `failed`. After a measured run, replace the placeholder with the p50/p95 from `benchmark_results_stats.csv`.

## Running the Benchmarks

Install Locust from the project extra if needed:

```bash
pip install '.[dev]'
# or: uv pip install locust
```

Then:

1. Start Postgres: `docker compose -f docker/docker-compose.yml up -d postgres`
2. Force offline mode: `export LLM_PROVIDER=mock`
3. Start API: `uvicorn app.main:app --workers 4`
4. Run load test: `bash scripts/benchmark.sh`

The headless Locust profile is **50 users**, spawn rate **10/s**, duration **1 minute**, writing `benchmark_results_*.csv` in the repo root.

**Offline invariant.** The API process must keep `LLM_PROVIDER=mock` (and should not export live `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` for this run). Researcher tools already degrade to empty evidence on provider errors; mock mode is what keeps planner/validator/synthesizer off the network so the CSV reflects graph and HTTP overhead.

**Workers.** `ResearchRunManager` keeps run status in process memory. With `--workers 4` and a non-sticky load balancer, a poll can hit a different worker than the `POST` and return 404. For an accurate lifecycle measurement on this codebase, start the API with `--workers 1` (or put a shared run store in front). `--workers 4` is appropriate once run state is shared across processes.

If `API_KEY` is set on the API, export the same value in the Locust shell so `FinancialAnalystUser` sends `X-API-Key`.
