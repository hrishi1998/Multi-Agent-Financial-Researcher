import os

# Keep Phase 1-7 suites unauthenticated and telemetry-quiet unless a test opts in.
os.environ.pop("API_KEY", None)
os.environ["ENABLE_TELEMETRY"] = "0"
os.environ.pop("ENABLE_HITL", None)
os.environ.pop("ENABLE_SEMANTIC_CACHE", None)
os.environ.pop("USE_REDIS", None)
