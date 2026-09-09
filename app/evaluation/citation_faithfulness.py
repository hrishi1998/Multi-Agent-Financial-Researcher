import os
import re
from typing import Iterable

from pydantic import BaseModel, Field

from app.api.schemas.reports import ResearchReport

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    flags=re.IGNORECASE,
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "in",
    "to",
    "for",
    "from",
    "with",
    "on",
    "is",
    "are",
    "was",
    "were",
}


class CitationAuditResult(BaseModel):
    citation_coverage: float
    claims_with_valid_citations: int
    total_claims: int
    uncited_claims: list[str] = Field(default_factory=list)
    faithfulness_score: float = 1.0


def _claims(report: ResearchReport) -> list[str]:
    return [item for item in [*report.key_findings, *report.bull_case, *report.bear_case] if item]


def _known_ids(report: ResearchReport) -> set[str]:
    ids = {item.evidence_id for item in report.evidence}
    for item in report.evidence_chain:
        ids.update(_UUID.findall(item.claim))
        ids.update(_UUID.findall(item.excerpt))
        ids.update(_UUID.findall(item.source_url_or_filing))
    return {item.lower() for item in ids}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOP and len(token) > 2
    }


def _overlap_score(claim: str, corpus: Iterable[str]) -> float:
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return 1.0
    best = 0.0
    for excerpt in corpus:
        other = _tokens(excerpt)
        if not other:
            continue
        best = max(best, len(claim_tokens & other) / len(claim_tokens))
    return best


def _excerpts(report: ResearchReport) -> list[str]:
    texts: list[str] = []
    for item in report.evidence:
        texts.extend(filter(None, [item.claim, item.raw_text, item.metric]))
    for item in report.evidence_chain:
        texts.extend(filter(None, [item.claim, item.excerpt, item.source_url_or_filing]))
    return texts


def _claim_numbers_supported(claim: str, report: ResearchReport) -> bool:
    numbers = set(_NUMBER.findall(claim.replace(",", "")))
    if not numbers:
        return True
    allowed = {f"{value:g}" for value in report.financial_metrics.values()}
    for metric in report.derived_metrics.values():
        if hasattr(metric, "current_value"):
            allowed.add(f"{metric.current_value:g}")
    evidence_values = {f"{item.value:g}" for item in report.evidence if item.value is not None}
    allowed.update(evidence_values)
    return all(number in allowed or any(number in token for token in allowed) for number in numbers)


def _offline_supports(claim: str, report: ResearchReport) -> bool:
    if not report.evidence and not report.evidence_chain:
        return False
    if not _claim_numbers_supported(claim, report):
        return False
    score = _overlap_score(claim, _excerpts(report))
    return score >= 0.15 or (not _UUID.search(claim) and _claim_numbers_supported(claim, report))


class CitationFaithfulnessEvaluator:
    def evaluate(self, report: ResearchReport) -> CitationAuditResult:
        claims = _claims(report)
        if not claims:
            return CitationAuditResult(
                citation_coverage=1.0,
                claims_with_valid_citations=0,
                total_claims=0,
                faithfulness_score=1.0,
            )
        known = _known_ids(report)
        cited = 0
        uncited: list[str] = []
        faithfulness_scores: list[float] = []
        use_heuristic = os.getenv("LLM_PROVIDER", "mock") == "mock" or not os.getenv("OPENAI_API_KEY")
        for claim in claims:
            mentioned = {item.lower() for item in _UUID.findall(claim)}
            if mentioned:
                valid = bool(mentioned & known)
                faithfulness_scores.append(1.0 if valid else 0.0)
                if valid:
                    cited += 1
                else:
                    uncited.append(claim)
                continue
            if use_heuristic and _offline_supports(claim, report):
                cited += 1
                faithfulness_scores.append(_overlap_score(claim, _excerpts(report)) or 0.8)
            else:
                uncited.append(claim)
                faithfulness_scores.append(0.0)
        return CitationAuditResult(
            citation_coverage=cited / len(claims),
            claims_with_valid_citations=cited,
            total_claims=len(claims),
            uncited_claims=uncited,
            faithfulness_score=sum(faithfulness_scores) / len(faithfulness_scores),
        )

    async def evaluate_with_optional_judge(self, report: ResearchReport) -> CitationAuditResult:
        result = self.evaluate(report)
        if os.getenv("LLM_PROVIDER") == "mock" or not os.getenv("OPENAI_API_KEY"):
            return result
        try:
            scores = await self._judge_claims(report)
            if scores:
                result.faithfulness_score = sum(scores) / len(scores)
        except Exception:
            return result
        return result

    async def _judge_claims(self, report: ResearchReport) -> list[float]:
        from langchain_openai import ChatOpenAI

        excerpts = "\n".join(_excerpts(report))[:4000]
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        scores: list[float] = []
        for claim in _claims(report):
            response = await model.ainvoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "Rate whether the evidence excerpt supports the claim. "
                            "Reply with a single float from 0.0 to 1.0."
                        ),
                    },
                    {"role": "human", "content": f"Claim: {claim}\nEvidence:\n{excerpts}"},
                ]
            )
            text = getattr(response, "content", str(response))
            match = re.search(r"0(?:\.\d+)?|1(?:\.0+)?", str(text))
            scores.append(float(match.group(0)) if match else 0.0)
        return scores
