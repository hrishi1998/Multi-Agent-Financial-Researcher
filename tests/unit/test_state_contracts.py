import operator
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from app.api.schemas.reports import Evidence, SourceType
from app.graph.state import ResearchState


def test_evidence_schema_validation():
    quantitative = Evidence(
        source="SEC EDGAR",
        source_type=SourceType.FILING,
        reporting_period="Q3-2025",
        metric="Revenue",
        value=1_234_000_000.0,
    )
    qualitative = Evidence(
        source="Reuters",
        source_type=SourceType.NEWS,
        raw_text="Management guided to mid-single-digit revenue growth.",
        claim="Guidance implies continued top-line expansion.",
    )

    assert quantitative.evidence_id
    assert qualitative.evidence_id
    assert quantitative.evidence_id != qualitative.evidence_id
    assert quantitative.confidence == 1.0
    assert qualitative.confidence == 1.0
    assert quantitative.value == 1_234_000_000.0
    assert qualitative.raw_text is not None


def test_evidence_reducer_concatenates_concurrent_updates():
    initial: dict[str, Any] = {"evidence": []}
    update1 = {
        "evidence": [
            Evidence(
                source="SEC EDGAR",
                source_type=SourceType.FILING,
                metric="Revenue",
                value=500.0,
            )
        ]
    }
    update2 = {
        "evidence": [
            Evidence(
                source="Yahoo Finance",
                source_type=SourceType.MARKET_API,
                metric="ClosePrice",
                value=182.4,
            )
        ]
    }

    merged = operator.add(initial["evidence"], update1["evidence"])
    merged = operator.add(merged, update2["evidence"])

    assert len(merged) == 2
    assert merged[0].source == "SEC EDGAR"
    assert merged[1].source == "Yahoo Finance"
    assert merged[0].evidence_id != merged[1].evidence_id


def test_research_state_annotated_reducers():
    hints = get_type_hints(ResearchState, include_extras=True)

    evidence_hint = hints["evidence"]
    assert get_origin(evidence_hint) is Annotated
    evidence_args = get_args(evidence_hint)
    assert evidence_args[1] is operator.add

    trace_hint = hints["execution_trace"]
    assert get_origin(trace_hint) is Annotated
    trace_args = get_args(trace_hint)
    assert trace_args[1] is operator.add
