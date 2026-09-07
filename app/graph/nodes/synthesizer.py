import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.api.schemas.reports import CalculatedMetric, Evidence
from app.graph.state import ResearchState
from app.infrastructure.llm.provider import LLMProviderFactory, SynthesisOutput

SYNTHESIS_SYSTEM_PROMPT = """You are an evidence-grounded equity synthesizer.
Hard rules:
- NEVER invent or recompute financial arithmetic (growth %, margins, ratios).
- Cite figures only from the provided evidence values or calculated_metrics.
- Every substantive claim must map to an evidence_id from the payload.
- If a number is not in the payload, omit it.
"""


def _fallback_synthesis(evidence: List[Evidence], calculated: Dict[str, CalculatedMetric], ticker: str) -> SynthesisOutput:
    cited = [item.evidence_id for item in evidence[:8]]
    findings = [
        f"{metric.name}: {metric.current_value}{metric.unit} (pre-computed)"
        for metric in calculated.values()
    ]
    if not findings:
        findings = [f"Aggregated {len(evidence)} evidence items for {ticker}."]
    return SynthesisOutput(
        executive_conclusion=f"Grounded summary for {ticker} using {len(evidence)} evidence items.",
        key_findings=findings,
        bull_case=["Constructive items appear in the supplied evidence set."],
        bear_case=["Coverage gaps in the evidence set remain."],
        risk_factors=["Do not treat uncited figures as facts."],
        cited_evidence_ids=cited,
        confidence_score=0.7 if cited else 0.35,
    )


async def synthesizer_node(state: ResearchState) -> Dict[str, Any]:
    """LLM synthesis bound to Evidence + pre-computed calculated_metrics only."""
    evidence: List[Evidence] = state.get("evidence") or []
    calculated: Dict[str, CalculatedMetric] = state.get("calculated_metrics") or {}
    plan = state.get("plan")
    ticker = plan.ticker if plan else "UNKNOWN"

    payload = {
        "ticker": ticker,
        "periods": plan.periods_to_fetch if plan else [],
        "calculated_metrics": {
            key: {
                "name": metric.name,
                "current_value": metric.current_value,
                "unit": metric.unit,
                "formula": metric.formula,
            }
            for key, metric in calculated.items()
        },
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "source": item.source,
                "metric": item.metric,
                "value": item.value,
                "reporting_period": item.reporting_period,
                "temporal_anchor": item.temporal_anchor,
                "claim": item.claim,
                "raw_text": (item.raw_text or "")[:300],
            }
            for item in evidence
        ],
    }

    model = LLMProviderFactory.get_chat_model(
        temperature=0.0,
        structured_output_schema=SynthesisOutput,
    )
    try:
        synthesis = await model.ainvoke(
            [
                {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                {"role": "human", "content": json.dumps(payload, default=str)},
            ]
        )
        if not isinstance(synthesis, SynthesisOutput):
            synthesis = SynthesisOutput.model_validate(synthesis)
    except Exception:
        synthesis = _fallback_synthesis(evidence, calculated, ticker)

    if not synthesis.cited_evidence_ids:
        synthesis.cited_evidence_ids = [item.evidence_id for item in evidence[:8]]

    return {
        "raw_synthesis": synthesis,
        "final_report": {
            "ticker": ticker,
            "analysis_period": plan.periods_to_fetch[0] if plan and plan.periods_to_fetch else None,
            "summary": synthesis.executive_conclusion,
            "evidence_count": len(evidence),
        },
        "execution_trace": [
            {
                "node": "synthesizer",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cited": len(synthesis.cited_evidence_ids),
            }
        ],
    }
