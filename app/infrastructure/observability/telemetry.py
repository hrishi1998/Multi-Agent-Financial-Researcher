import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def configure_langsmith() -> None:
    """Map LANGSMITH_* settings onto the LangChain / LangGraph tracing env vars."""
    tracing = os.getenv("LANGSMITH_TRACING", "").strip().lower()
    if tracing in {"1", "true", "yes"}:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    if os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGCHAIN_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]
    if os.getenv("LANGSMITH_PROJECT") and not os.getenv("LANGCHAIN_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = os.environ["LANGSMITH_PROJECT"]


def _span_exporter() -> Any:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=endpoint)
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    return ConsoleSpanExporter()


def setup_telemetry(app: Any) -> None:
    """Instrument FastAPI, httpx, and SQLAlchemy. Failures never take the app down."""
    configure_langsmith()
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.getenv("OTEL_SERVICE_NAME", "multi-agent-financial-researcher")
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(_span_exporter()))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        logger.info("OpenTelemetry instrumentation enabled.")
    except Exception:
        logger.exception("OpenTelemetry setup failed; continuing without telemetry.")
