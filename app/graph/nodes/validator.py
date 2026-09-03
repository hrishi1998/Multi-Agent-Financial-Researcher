from typing import Dict, List, Any
from app.api.schemas.reports import ValidationResult, ValidationIssue, RawMetric
from app.graph.state import ResearchState


def run_deterministic_validation(raw_metrics: List[RawMetric], required_metrics: List[str]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    # 1. Check Missing Metrics
    present_metric_names = {m.name for m in raw_metrics}
    for req in required_metrics:
        if req not in present_metric_names:
            issues.append(
                ValidationIssue(
                    field=req,
                    issue_type="MISSING_METRIC",
                    severity="CRITICAL",
                    description=f"Required metric '{req}' was not extracted from primary filings.",
                    suggested_action=f"Retry SEC or Web extraction for missing concept: {req}",
                )
            )

    # 2. Arithmetic & Relationship Checks per period
    by_period: Dict[str, Dict[str, float]] = {}
    for m in raw_metrics:
        if m.period not in by_period:
            by_period[m.period] = {}
        by_period[m.period][m.name] = m.value

    for period, metrics in by_period.items():
        revenue = metrics.get("Revenue")
        gross_profit = metrics.get("GrossProfit")

        if revenue is not None and gross_profit is not None:
            if gross_profit > revenue and revenue > 0:
                issues.append(
                    ValidationIssue(
                        field=f"GrossProfit_{period}",
                        issue_type="ARITHMETIC_INCONSISTENCY",
                        severity="CRITICAL",
                        description=f"Gross Profit ({gross_profit}) cannot exceed Total Revenue ({revenue}) for {period}.",
                        suggested_action="Verify XBRL line item tags for Gross Margin vs Operating Revenue.",
                    )
                )

        if revenue is not None and revenue < 0:
            issues.append(
                ValidationIssue(
                    field=f"Revenue_{period}",
                    issue_type="NEGATIVE_VALUE_CONSTRAINT",
                    severity="WARNING",
                    description=f"Negative revenue observed: {revenue} in {period}.",
                    suggested_action="Check if accounting restatement or contra-revenue was recorded.",
                )
            )

    return issues


async def validator_node(state: ResearchState) -> Dict[str, Any]:
    """
    Validation Stage: Runs deterministic audits on collected facts.
    """
    raw_data = state.get("raw_financial_data", [])
    plan = state.get("plan")
    required = plan.required_raw_metrics if plan else ["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"]

    deterministic_issues = run_deterministic_validation(raw_data, required)

    critical_issues = [i for i in deterministic_issues if i.severity == "CRITICAL"]
    passed = len(critical_issues) == 0

    validation_result = ValidationResult(
        is_valid=passed,
        deterministic_passed=passed,
        semantic_passed=True,  # Default True prior to semantic stage
        issues=deterministic_issues,
        retry_needed=not passed and state.get("retry_count", 0) < (plan.max_retries if plan else 2),
        retry_directive=f"Re-fetch missing or inconsistent items: {[i.field for i in critical_issues]}" if not passed else None
    )

    return {"validation_result": validation_result}
