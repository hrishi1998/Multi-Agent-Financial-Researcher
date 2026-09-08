#!/usr/bin/env bash
# Headless Locust run against a locally hosted API.
# Benchmarks infrastructure (FastAPI + LangGraph), not live LLM/SEC latency.
# The API process must be started with LLM_PROVIDER=mock.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

HOST="${HOST:-http://localhost:8000}"
USERS="${USERS:-50}"
SPAWN_RATE="${SPAWN_RATE:-10}"
RUN_TIME="${RUN_TIME:-1m}"
CSV="${CSV:-benchmark_results}"

if [[ -x "${ROOT}/.venv/bin/locust" ]]; then
  LOCUST_BIN="${ROOT}/.venv/bin/locust"
else
  LOCUST_BIN="locust"
fi

echo "Infrastructure benchmark"
echo "  host=${HOST} users=${USERS} spawn_rate=${SPAWN_RATE} run_time=${RUN_TIME}"
echo "  csv=${CSV}"
echo "  Ensure the API is running with LLM_PROVIDER=mock (no live OpenAI/Anthropic/SEC)."

"${LOCUST_BIN}" \
  -f tests/load/locustfile.py \
  --headless \
  -u "${USERS}" \
  -r "${SPAWN_RATE}" \
  --run-time "${RUN_TIME}" \
  --host "${HOST}" \
  --csv="${CSV}"
