import pytest

from app.api.schemas.reports import CalculatedMetric, Evidence, SourceType
from app.graph.nodes.planner import planner_node
from app.graph.nodes.synthesizer import synthesizer_node
from app.graph.nodes.validator import validator_node
from app.graph.state import ResearchPlan
from app.infrastructure.llm.provider import SynthesisOutput


def _base_state(**overrides):
    state = {
        "run_id": "llm-node-test",
        "user_query": "Analyze NVDA Q3-2025",
        "plan": None,
        "evidence": [],
        "raw_financial_data": [],
        "market_data": {},
        "qualitative_evidence": [],
        "rag_context": [],
        "calculated_metrics": {},
        "validation_result": None,
        "retry_count": 0,
        "iteration_count": 0,
        "max_iterations": 2,
        "is_validated": False,
        "execution_trace": [],
        "raw_synthesis": None,
        "final_report": None,
        "events": [],
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,expected_ticker",
    [
        ("Analyze Apple's last 2 quarters of revenue and profitability", "AAPL"),
        ("How is Tesla doing this year?", "TSLA"),
        ("Analyze NVDA Q3-2025", "NVDA"),
    ],
)
async def test_planner_decomposes_query_into_research_plan(query: str, expected_ticker: str):
    result = await planner_node(_base_state(user_query=query))
    plan = result["plan"]
    assert isinstance(plan, ResearchPlan)
    assert plan.ticker == expected_ticker
    assert plan.company_name
    assert plan.periods_to_fetch
    assert plan.required_raw_metrics
    assert plan.target_questions


@pytest.mark.asyncio
async def test_synthesizer_cites_evidence_and_fills_cases():
    evidence = [
        Evidence(
            source="SEC EDGAR",
            source_type=SourceType.FILING,
            metric="Revenue",
            value=1000.0,
            reporting_period="Q3-2025",
            claim="Revenue printed 1000.",
        ),
        Evidence(
            source="Web / News",
            source_type=SourceType.NEWS,
            raw_text="Demand commentary remains constructive.",
            claim="Street tone is constructive.",
            reporting_period="Q3-2025",
        ),
    ]
    calculated = {
        "Mock_Margin": CalculatedMetric(
            name="Gross Margin",
            formula="(Gross Profit / Revenue) * 100",
            current_value=40.0,
            unit="%",
        )
    }
    result = await synthesizer_node(
        _base_state(
            plan=ResearchPlan(
                ticker="AAPL",
                company_name="Apple Inc.",
                periods_to_fetch=["Q3-2025"],
                required_raw_metrics=["Revenue"],
                target_questions=["profitability"],
            ),
            evidence=evidence,
            calculated_metrics=calculated,
        )
    )
    synthesis = result["raw_synthesis"]
    assert isinstance(synthesis, SynthesisOutput)
    assert synthesis.key_findings
    assert synthesis.bull_case
    assert synthesis.bear_case
    assert synthesis.cited_evidence_ids
    assert set(synthesis.cited_evidence_ids) <= {item.evidence_id for item in evidence} | {"unspecified"}


@pytest.mark.asyncio
async def test_semantic_validator_flags_stale_period():
    stale = Evidence(
        source="Web / News",
        source_type=SourceType.NEWS,
        raw_text="Results discussed in the 2021 10-K remain the only cited year.",
        claim="Using 2021 performance as if it were current.",
        reporting_period="2021",
        temporal_anchor="2021",
    )
    result = await validator_node(
        _base_state(
            plan=ResearchPlan(
                ticker="AAPL",
                company_name="Apple Inc.",
                periods_to_fetch=["Q3-2025"],
                required_raw_metrics=["Revenue"],
                target_questions=["current year"],
            ),
            evidence=[stale],
            iteration_count=0,
            max_iterations=1,
        )
    )
    validation = result["validation_result"]
    issue_types = {issue.issue_type for issue in validation.issues}
    assert "PERIOD_INCONSISTENCY" in issue_types
    assert validation.semantic_passed is False
