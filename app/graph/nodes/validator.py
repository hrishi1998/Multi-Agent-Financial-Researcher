import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.api.schemas.reports import (
    Evidence,
    RawMetric,
    SourceType,
    ValidationIssue,
    ValidationResult,
)
from app.graph.quality import missing_source_warnings
from app.graph.state import ResearchState
from app.infrastructure.llm.provider import LLMProviderFactory, SemanticAudit


def run_deterministic_validation(
    raw_metrics: List[RawMetric], required_metrics: List[str]
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

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


def _evidence_to_raw_metrics(evidence: List[Evidence]) -> List[RawMetric]:
    raw: List[RawMetric] = []
    for item in evidence:
        if item.metric is None or item.value is None:
            continue
        raw.append(
            RawMetric(
                name=item.metric,
                period=item.reporting_period or item.temporal_anchor or "unknown",
                value=item.value,
                source_filing=item.source,
            )
        )
    return raw


def _years_in(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    return set(re.findall(r"20\d{2}", text))


def _temporal_and_conflict_issues(
    evidence: List[Evidence], requested_periods: List[str]
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    wanted_years = set()
    for period in requested_periods:
        wanted_years.update(_years_in(period))

    seen: Dict[tuple[str, Optional[str]], float] = {}
    for item in evidence:
        period = item.reporting_period or item.temporal_anchor
        item_years = _years_in(period) | _years_in(item.raw_text)
        if wanted_years and item_years and item_years.isdisjoint(wanted_years):
            if (
                item.source_type in {SourceType.NEWS, SourceType.INTERNAL_DOCUMENT}
                or item.value is None
            ):
                issues.append(
                    ValidationIssue(
                        field=item.evidence_id,
                        issue_type="PERIOD_INCONSISTENCY",
                        severity="CRITICAL",
                        description=(
                            f"Evidence from {item.source} is anchored to {period or item_years} "
                            f"but the plan requested {requested_periods}."
                        ),
                        suggested_action="Discard stale qualitative evidence or re-fetch the requested period.",
                    )
                )
        if item.metric and item.value is not None:
            key = (item.metric, item.reporting_period)
            prior = seen.get(key)
            if prior is not None and abs(prior - item.value) > 1e-6:
                issues.append(
                    ValidationIssue(
                        field=item.metric,
                        issue_type="CONFLICTING_VALUES",
                        severity="WARNING",
                        description=f"Conflicting {item.metric} values {prior} vs {item.value} for {item.reporting_period}.",
                        suggested_action="Prefer primary SEC facts over secondary quotes.",
                    )
                )
            seen[key] = item.value
    return issues


async def _semantic_audit(evidence: List[Evidence], requested_periods: List[str]) -> SemanticAudit:
    qualitative = [
        item
        for item in evidence
        if item.source_type in {SourceType.NEWS, SourceType.INTERNAL_DOCUMENT} or item.raw_text
    ]
    payload = [
        {
            "evidence_id": item.evidence_id,
            "source": item.source,
            "reporting_period": item.reporting_period,
            "temporal_anchor": item.temporal_anchor,
            "claim": item.claim,
            "raw_text": (item.raw_text or "")[:400],
        }
        for item in qualitative
    ]
    model = LLMProviderFactory.get_chat_model(
        temperature=0.0,
        structured_output_schema=SemanticAudit,
    )
    try:
        return await model.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Audit qualitative financial evidence for temporal hallucinations and "
                        "period mismatches. Do not invent numbers. Flag excerpts whose "
                        "temporal_anchor or reporting_period does not match the requested periods."
                    ),
                },
                {
                    "role": "human",
                    "content": json.dumps(
                        {"requested_periods": requested_periods, "evidence": payload},
                        default=str,
                    ),
                },
            ]
        )
    except Exception:
        return SemanticAudit(semantic_passed=True, issues=[])


async def validator_node(state: ResearchState) -> Dict[str, Any]:
    """Deterministic accounting checks + semantic temporal audit, with a bounded retry gate."""
    current_iteration = state.get("iteration_count", 0) + 1
    max_iterations = state.get("max_iterations", 2)
    plan = state.get("plan")
    evidence: List[Evidence] = state.get("evidence") or []
    required = (
        plan.required_raw_metrics
        if plan
        else ["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"]
    )
    requested_periods = plan.periods_to_fetch if plan else []

    raw_metrics = list(state.get("raw_financial_data") or []) or _evidence_to_raw_metrics(evidence)
    deterministic_issues = run_deterministic_validation(raw_metrics, required)
    heuristic_semantic = _temporal_and_conflict_issues(evidence, requested_periods)
    llm_audit = await _semantic_audit(evidence, requested_periods)
    if not isinstance(llm_audit, SemanticAudit):
        llm_audit = SemanticAudit.model_validate(llm_audit)

    semantic_issues = heuristic_semantic + list(llm_audit.issues)
    all_issues = deterministic_issues + semantic_issues
    deterministic_passed = not any(issue.severity == "CRITICAL" for issue in deterministic_issues)
    semantic_passed = not any(issue.severity == "CRITICAL" for issue in semantic_issues)
    critical = [issue for issue in all_issues if issue.severity == "CRITICAL"]

    if current_iteration == 1 and current_iteration < max_iterations:
        is_validated = False
        retry_needed = True
        retry_directive = (
            f"Re-fetch missing or inconsistent items: {[issue.field for issue in critical]}"
            if critical
            else "Run a second evidence pass to confirm completeness before synthesis."
        )
    else:
        is_validated = deterministic_passed and semantic_passed
        retry_needed = bool(critical) and current_iteration < max_iterations
        retry_directive = (
            f"Re-fetch missing or inconsistent items: {[issue.field for issue in critical]}"
            if retry_needed
            else None
        )

    validation_result = ValidationResult(
        is_valid=is_validated and not critical,
        deterministic_passed=deterministic_passed,
        semantic_passed=semantic_passed,
        issues=all_issues,
        retry_needed=retry_needed,
        retry_directive=retry_directive,
    )

    source_warnings = missing_source_warnings(evidence)
    status = "passed" if is_validated else "failed"
    if is_validated and (
        source_warnings or any(issue.severity == "WARNING" for issue in all_issues)
    ):
        status = "warning"

    return {
        "iteration_count": current_iteration,
        "is_validated": is_validated,
        "validation_result": validation_result,
        "execution_trace": [
            {
                "node": "validator",
                "status": status,
                "warnings": source_warnings,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
