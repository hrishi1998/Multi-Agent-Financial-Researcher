"""Locust suite for infrastructure throughput — not third-party API latency.

The API under test MUST run with `LLM_PROVIDER=mock`. Researcher nodes already
catch provider failures, but mock mode keeps the planner/validator/synthesizer
offline so results measure FastAPI + LangGraph fan-out, not OpenAI/SEC/Yahoo.
"""

from __future__ import annotations

import os
import random
import time

from locust import HttpUser, between, events, task

SAMPLE_QUERIES = (
    "Analyze NVDA Q3-2025",
    "Evaluate AAPL profitability for Q3-2025",
    "Review MSFT revenue quality in Q3-2025",
)
POLL_INTERVAL_SECONDS = 2.0
LIFECYCLE_TIMEOUT_SECONDS = 90.0
TERMINAL_STATUSES = frozenset({"completed", "failed"})


class FinancialAnalystUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        api_key = os.getenv("API_KEY")
        if api_key:
            self.client.headers["X-API-Key"] = api_key

    @task(3)
    def health_baseline(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(1)
    def full_research_lifecycle(self) -> None:
        query = random.choice(SAMPLE_QUERIES)
        started = time.perf_counter()
        exception: Exception | None = None
        response_length = 0

        with self.client.post(
            "/api/v1/research",
            json={"query": query},
            name="POST /api/v1/research",
            catch_response=True,
        ) as created:
            if created.status_code != 202:
                created.failure(f"expected 202, got {created.status_code}")
                exception = RuntimeError(f"research create failed: {created.status_code}")
            else:
                payload = created.json()
                run_id = payload.get("run_id")
                if not run_id:
                    created.failure("202 response missing run_id")
                    exception = RuntimeError("missing run_id")
                else:
                    created.success()
                    exception = self._poll_until_terminal(run_id)
                    if exception is None:
                        response_length = 1

        elapsed_ms = (time.perf_counter() - started) * 1000
        events.request.fire(
            request_type="Flow",
            name="Full Research Lifecycle",
            response_time=elapsed_ms,
            response_length=response_length,
            exception=exception,
            context=self.context(),
        )

    def _poll_until_terminal(self, run_id: str) -> Exception | None:
        deadline = time.perf_counter() + LIFECYCLE_TIMEOUT_SECONDS
        last_status = "unknown"
        while time.perf_counter() < deadline:
            with self.client.get(
                f"/api/v1/research/{run_id}",
                name="GET /api/v1/research/{run_id}",
                catch_response=True,
            ) as status_response:
                if status_response.status_code != 200:
                    status_response.failure(f"expected 200, got {status_response.status_code}")
                    return RuntimeError(f"status poll failed: {status_response.status_code}")
                body = status_response.json()
                last_status = body.get("status") or "unknown"
                status_response.success()
                if last_status in TERMINAL_STATUSES:
                    if last_status == "failed":
                        return RuntimeError(body.get("error") or "research run failed")
                    return None
            time.sleep(POLL_INTERVAL_SECONDS)
        return TimeoutError(f"research run did not finish (last status={last_status})")
