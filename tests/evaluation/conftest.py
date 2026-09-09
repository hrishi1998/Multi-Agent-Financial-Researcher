import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ.pop("ENABLE_HITL", None)
os.environ.pop("OPENAI_API_KEY", None)
