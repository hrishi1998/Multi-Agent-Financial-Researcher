import os

# Keep Phase 1-7 suites unauthenticated and telemetry-quiet unless a test opts in.
os.environ.pop("API_KEY", None)
os.environ["ENABLE_TELEMETRY"] = "0"
