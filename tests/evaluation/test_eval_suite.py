from uuid import uuid4

import pytest

from app.api.schemas.reports import (
    CalculatedMetric,
    Evidence,
    EvidenceItem,
    ResearchReport,
    SourceType,
    ValidationResult,
)
from app.evaluation.citation_faithfulness import CitationFaithfulnessEvaluator
from app.evaluation.dataset import load_dataset
from app.evaluation.numerical_auditor import NumericalAccuracyEvaluator
from app.evaluation.runner import evaluate_dataset, render_scorecard


def _base_report() -> ResearchReport:
    case = load_dataset().cases[0]
    evidence_id = str(uuid4())
    return ResearchReport(
        run_id="eval-report-1",
        company_name=case.company_name,
        ticker=case.ticker,
        analysis_period=case.analysis_period,
        executive_conclusion="Grounded NVDA summary.",
        key_findings=[f"Revenue printed {case.canonical_metrics['Revenue']} [{evidence_id}]"],
        bull_case=["Demand commentary is supported by filing evidence."],
        bear_case=["Export-control risk remains a constraint."],
        risk_factors=[],
        financial_metrics=dict(case.canonical_metrics),
        derived_metrics={
            "GrossMargin": CalculatedMetric(
                name="Gross Margin",
                formula="(Gross Profit / Revenue) * 100",
                current_value=case.canonical_derived["GrossMargin"],
                unit="%",
            ),
            "OperatingMargin": CalculatedMetric(
                name="Operating Margin",
                formula="(Operating Income / Revenue) * 100",
                current_value=case.canonical_derived["OperatingMargin"],
                unit="%",
            ),
        },
        evidence=[
            Evidence(
                evidence_id=evidence_id,
                source="SEC EDGAR",
                source_type=SourceType.FILING,
                metric="Revenue",
                value=case.canonical_metrics["Revenue"],
                claim=f"Revenue of {case.canonical_metrics['Revenue']} from 10-Q.",
                raw_text="NVIDIA Data Center revenue represented over 80% of total revenue.",
            )
        ],
        evidence_chain=[
            EvidenceItem(
                claim="Revenue printed above the prior-year quarter.",
                observed_facts=[],
                derived_metrics=[],
                source_url_or_filing="10-Q",
                excerpt=f"Revenue {case.canonical_metrics['Revenue']}",
                temporal_anchor=case.analysis_period,
                confidence_score=0.9,
            )
        ],
        validation_audit=ValidationResult(
            is_valid=True,
            deterministic_passed=True,
            semantic_passed=True,
        ),
        aggregate_confidence_score=0.9,
    )


def test_numerical_evaluator_catches_hallucinations():
    case = load_dataset().cases[0]
    report = _base_report()
    report.financial_metrics["Revenue"] = case.canonical_metrics["Revenue"] * 1.25
    report.financial_metrics["InventedEBITDA"] = 99.0
    result = NumericalAccuracyEvaluator().evaluate(report, case)
    assert result.metric_accuracy_score < 1.0
    assert any("Revenue" in item for item in result.mismatches)
    assert "InventedEBITDA" in result.phantom_metrics


def test_citation_evaluator_catches_missing_evidence():
    report = _base_report()
    good = CitationFaithfulnessEvaluator().evaluate(report)
    report.key_findings = [
        "Invented revenue spike [00000000-0000-0000-0000-000000000000] without a source."
    ]
    bad = CitationFaithfulnessEvaluator().evaluate(report)
    assert good.citation_coverage > bad.citation_coverage
    assert bad.uncited_claims


@pytest.mark.asyncio
async def test_end_to_end_evaluation_offline():
    scorecard = await evaluate_dataset(offline=True)
    assert scorecard.cases
    assert scorecard.numerical_precision == 1.0
    assert scorecard.citation_provenance_rate == 1.0
    assert scorecard.hallucination_count == 0
    assert scorecard.passed
    markdown = render_scorecard(scorecard)
    assert "Evaluation Scorecard" in markdown
    assert "PASS" in markdown
