import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[2] / "tests" / "evaluation" / "ground_truth" / "dataset.json"
)


class GroundTruthCase(BaseModel):
    case_id: str
    ticker: str
    company_name: str
    analysis_period: str
    query: str
    canonical_metrics: dict[str, float]
    canonical_derived: dict[str, float]
    known_facts: list[str] = Field(default_factory=list)


class EvaluationDataset(BaseModel):
    version: str = "1.0"
    cases: list[GroundTruthCase]


def load_dataset(path: str | Path | None = None) -> EvaluationDataset:
    target = Path(path) if path else DEFAULT_DATASET
    payload: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    return EvaluationDataset.model_validate(payload)
