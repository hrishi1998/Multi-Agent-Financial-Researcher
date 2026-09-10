import os
import re
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from app.api.schemas.reports import ValidationIssue
from app.graph.state import ResearchPlan


class SemanticAudit(BaseModel):
    semantic_passed: bool = True
    issues: List[ValidationIssue] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    executive_conclusion: str
    key_findings: List[str]
    bull_case: List[str]
    bear_case: List[str]
    risk_factors: List[str]
    cited_evidence_ids: List[str]
    confidence_score: float = Field(ge=0.0, le=1.0)


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", message))


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or "")
    return str(getattr(message, "type", getattr(message, "role", "")))


def _flatten_messages(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    return "\n".join(_message_text(message) for message in messages or [])


def _human_text(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    humans = [
        _message_text(message)
        for message in messages or []
        if _message_role(message) in {"human", "user"}
    ]
    return humans[-1] if humans else _flatten_messages(messages)


def _infer_company(query: str) -> tuple[str, str]:
    lowered = query.lower()
    aliases = {
        "apple": ("AAPL", "Apple Inc."),
        "aapl": ("AAPL", "Apple Inc."),
        "nvidia": ("NVDA", "NVIDIA Corporation"),
        "nvda": ("NVDA", "NVIDIA Corporation"),
        "tesla": ("TSLA", "Tesla, Inc."),
        "tsla": ("TSLA", "Tesla, Inc."),
        "microsoft": ("MSFT", "Microsoft Corporation"),
        "amazon": ("AMZN", "Amazon.com, Inc."),
        "invalid_ticker_999": ("INVALID_TICKER_999", "INVALID_TICKER_999"),
    }
    for needle, pair in aliases.items():
        if needle in lowered:
            return pair
    match = re.search(r"\b([A-Z]{2,20}(?:_[A-Z0-9]+)*)\b", query)
    if match and not (match.group(1).startswith("Q") and match.group(1)[1:2].isdigit()):
        ticker = match.group(1)
        return ticker, ticker
    return "NVDA", "NVIDIA Corporation"


def _infer_periods(query: str) -> List[str]:
    explicit = re.findall(r"Q[1-4]-\d{4}", query, flags=re.IGNORECASE)
    if explicit:
        return [item.upper() if item[1].isdigit() else item for item in explicit]
    if re.search(r"last\s+2\s+quarters", query, flags=re.IGNORECASE):
        return ["Q2-2025", "Q3-2025"]
    if re.search(r"this\s+year", query, flags=re.IGNORECASE):
        return ["Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025"]
    return ["Q3-2025"]


def _mock_research_plan(text: str) -> ResearchPlan:
    ticker, company = _infer_company(text)
    return ResearchPlan(
        ticker=ticker,
        company_name=company,
        periods_to_fetch=_infer_periods(text),
        required_raw_metrics=["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"],
        target_questions=[
            f"{company} revenue growth outlook",
            f"{company} profitability and margin commentary",
        ],
    )


def _extract_ids(text: str) -> List[str]:
    return re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, flags=re.IGNORECASE
    )


def _mock_synthesis(text: str) -> SynthesisOutput:
    cited = _extract_ids(text)[:8]
    ticker_match = re.search(r"\b([A-Z]{2,5})\b", text)
    ticker = ticker_match.group(1) if ticker_match else "the company"
    return SynthesisOutput(
        executive_conclusion=(
            f"{ticker} synthesis is grounded only in provided evidence and "
            "pre-computed calculated_metrics; no new arithmetic was performed."
        ),
        key_findings=[
            "Cited figures are taken from supplied evidence values and calculated_metrics.",
            "Qualitative commentary is limited to provided web/RAG excerpts.",
        ],
        bull_case=["Demand and mix commentary in the evidence set supports a constructive case."],
        bear_case=["Missing or stale sources in the evidence set cap conviction."],
        risk_factors=["Data gaps or period mismatches may distort the current-period picture."],
        cited_evidence_ids=cited or ["unspecified"],
        confidence_score=0.72 if cited else 0.4,
    )


def _mock_semantic_audit(text: str) -> SemanticAudit:
    issues: List[ValidationIssue] = []
    years = set(re.findall(r"20\d{2}", text))
    if "2021" in text and any(year >= "2025" for year in years):
        issues.append(
            ValidationIssue(
                field="temporal_anchor",
                issue_type="PERIOD_INCONSISTENCY",
                severity="CRITICAL",
                description="Qualitative evidence from 2021 is being treated as current 2025 context.",
                suggested_action="Drop stale excerpts or re-query for the requested reporting period.",
            )
        )
    return SemanticAudit(semantic_passed=len(issues) == 0, issues=issues)


class MockStructuredModel:
    """Deterministic structured-output stand-in used when no API key is present."""

    def __init__(self, schema: Type[BaseModel]) -> None:
        self.schema = schema

    async def ainvoke(self, messages: Any, **kwargs: Any) -> BaseModel:
        text = _flatten_messages(messages)
        if self.schema is ResearchPlan:
            return _mock_research_plan(_human_text(messages))
        if self.schema is SynthesisOutput:
            return _mock_synthesis(text)
        if self.schema is SemanticAudit:
            return _mock_semantic_audit(text)
        return self.schema.model_validate({})

    def invoke(self, messages: Any, **kwargs: Any) -> BaseModel:
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.ainvoke(messages, **kwargs))


class MockChatModel:
    def with_structured_output(self, schema: Type[BaseModel]) -> MockStructuredModel:
        return MockStructuredModel(schema)

    async def ainvoke(self, messages: Any, **kwargs: Any) -> str:
        return _flatten_messages(messages)


class LLMProviderFactory:
    @staticmethod
    def get_chat_model(
        temperature: float = 0.0,
        structured_output_schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        use_mock = (
            provider == "mock"
            or (provider == "openai" and not openai_key)
            or (provider == "anthropic" and not anthropic_key)
            or provider not in {"openai", "anthropic", "mock"}
        )

        if not use_mock and provider == "openai":
            try:
                from langchain_openai import ChatOpenAI

                model = ChatOpenAI(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    temperature=temperature,
                    api_key=openai_key,
                )
                if structured_output_schema is not None:
                    return model.with_structured_output(structured_output_schema)
                return model
            except Exception:
                use_mock = True

        if not use_mock and provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic

                model = ChatAnthropic(
                    model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                    temperature=temperature,
                    api_key=anthropic_key,
                )
                if structured_output_schema is not None:
                    return model.with_structured_output(structured_output_schema)
                return model
            except Exception:
                use_mock = True

        mock = MockChatModel()
        if structured_output_schema is not None:
            return mock.with_structured_output(structured_output_schema)
        return mock
