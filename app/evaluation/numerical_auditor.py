from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel, Field

from app.api.schemas.reports import CalculatedMetric, ResearchReport
from app.evaluation.dataset import GroundTruthCase

RELATIVE_TOLERANCE = Decimal("0.005")


class NumericalAuditResult(BaseModel):
    metric_accuracy_score: float
    matching_metrics: int
    total_required_metrics: int
    mismatches: list[str] = Field(default_factory=list)
    phantom_metrics: list[str] = Field(default_factory=list)


def _normalize(name: str) -> str:
    return "".join(char for char in name.lower() if char.isalnum())


def _within_tolerance(actual: float, expected: float) -> bool:
    expected_d = Decimal(str(expected))
    actual_d = Decimal(str(actual))
    if expected_d == 0:
        return actual_d == 0
    return abs(actual_d - expected_d) / abs(expected_d) <= RELATIVE_TOLERANCE


def _derived_lookup(report: ResearchReport) -> dict[str, float]:
    found: dict[str, float] = {}
    for key, metric in report.derived_metrics.items():
        if isinstance(metric, CalculatedMetric):
            found[_normalize(key)] = metric.current_value
            found[_normalize(metric.name)] = metric.current_value
        elif isinstance(metric, dict) and "current_value" in metric:
            found[_normalize(key)] = float(metric["current_value"])
            if metric.get("name"):
                found[_normalize(str(metric["name"]))] = float(metric["current_value"])
    return found


def _financial_lookup(report: ResearchReport) -> dict[str, float]:
    return {_normalize(name): value for name, value in report.financial_metrics.items()}


class NumericalAccuracyEvaluator:
    """Strict Decimal comparison of GAAP and derived metrics. Never uses an LLM."""

    def evaluate(self, report: ResearchReport, case: GroundTruthCase) -> NumericalAuditResult:
        financials = _financial_lookup(report)
        derived = _derived_lookup(report)
        required = list(case.canonical_metrics.items()) + list(case.canonical_derived.items())
        matching = 0
        mismatches: list[str] = []
        for name, expected in required:
            actual = financials.get(_normalize(name))
            if actual is None:
                actual = derived.get(_normalize(name))
            if actual is None or not _within_tolerance(actual, expected):
                mismatches.append(
                    f"{name}: expected {expected}, got {actual if actual is not None else 'missing'}"
                )
            else:
                matching += 1

        evidence_metrics = {
            _normalize(item.metric)
            for item in report.evidence
            if item.metric
        }
        allowed = {
            _normalize(name)
            for name in list(case.canonical_metrics) + list(case.canonical_derived)
        }
        allowed.update({"grossmargin", "operatingmargin", "mockmargin"})
        phantom = []
        for name in report.financial_metrics:
            key = _normalize(name)
            if key not in evidence_metrics and key not in allowed:
                phantom.append(name)
        for key, metric in report.derived_metrics.items():
            label = metric.name if isinstance(metric, CalculatedMetric) else key
            if _normalize(str(label)) not in allowed and _normalize(key) not in allowed:
                phantom.append(str(label))

        total = len(required) or 1
        return NumericalAuditResult(
            metric_accuracy_score=matching / total,
            matching_metrics=matching,
            total_required_metrics=len(required),
            mismatches=mismatches,
            phantom_metrics=sorted(set(phantom)),
        )


def flatten_metric_names(names: Iterable[str]) -> set[str]:
    return {_normalize(name) for name in names}
