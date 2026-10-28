"""Load the trained real-data models and score canonical applicants.

The serving process and the adapter feasibility check share this module, so the
feature mapping used at audit time is exactly the mapping used at serve time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from config_loader import REPO_ROOT
from schemas import Applicant, ModelResponse
from targets.real.features import (
    FeatureProfile,
    map_applicant,
    validate_row,
)

ARTIFACT_DIR = REPO_ROOT / "data" / "real" / "artifacts"
APPROVAL_THRESHOLD = 500.0  # P(favourable) >= 0.5 on a 0-1000 score


class RealModelUnavailable(RuntimeError):
    """Raised when a trained artifact or its metrics file is missing."""


class InfeasibleApplicant(ValueError):
    """Raised when a mapped applicant falls outside the training domain."""


@dataclass(frozen=True)
class RealModel:
    name: str
    pipeline: Any
    metrics: dict[str, Any]
    profile: FeatureProfile


def metrics_path(model_name: str) -> Path:
    return ARTIFACT_DIR / f"{model_name}.metrics.json"


def artifact_path(model_name: str) -> Path:
    path = metrics_path(model_name)
    if not path.exists():
        raise RealModelUnavailable(
            f"Missing {path.relative_to(REPO_ROOT)}. "
            "Run: .venv\\Scripts\\python -m targets.real.train"
        )
    metrics = json.loads(path.read_text(encoding="utf-8"))
    return ARTIFACT_DIR / metrics["artifact"]


@lru_cache(maxsize=4)
def load_real_model(model_name: str) -> RealModel:
    path = metrics_path(model_name)
    if not path.exists():
        raise RealModelUnavailable(
            f"Missing {path.relative_to(REPO_ROOT)}. "
            "Run: .venv\\Scripts\\python -m targets.real.train"
        )
    metrics = json.loads(path.read_text(encoding="utf-8"))
    artifact = ARTIFACT_DIR / metrics["artifact"]
    if not artifact.exists():
        raise RealModelUnavailable(
            f"Missing {artifact.relative_to(REPO_ROOT)}. "
            "Run: .venv\\Scripts\\python -m targets.real.train"
        )
    profile = FeatureProfile(
        quantile_grids={k: list(v) for k, v in metrics["quantile_grids"].items()},
        ranges={k: list(v) for k, v in metrics["ranges"].items()},
        categories={k: list(v) for k, v in metrics["categories"].items()},
    )
    return RealModel(
        name=model_name,
        pipeline=joblib.load(artifact),
        metrics=metrics,
        profile=profile,
    )


def available_models() -> list[str]:
    found: list[str] = []
    for path in sorted(ARTIFACT_DIR.glob("*.metrics.json")):
        name = path.name.removesuffix(".metrics.json")
        try:
            artifact_path(name)
        except RealModelUnavailable:
            continue
        found.append(name)
    return found


def score_applicants(model_name: str, applicants: list[Applicant]) -> list[ModelResponse]:
    model = load_real_model(model_name)
    rows: list[dict[str, Any]] = []
    for applicant in applicants:
        row = map_applicant(model_name, applicant, model.profile)
        violations = validate_row(model_name, row, model.profile)
        if violations:
            raise InfeasibleApplicant(
                f"applicant {applicant.id}: " + "; ".join(violations)
            )
        rows.append(row)
    frame = pd.DataFrame(rows)
    if model_name == "uci_credit_default":
        probability_good = 1.0 - model.pipeline.predict_proba(frame)[:, 1]
    else:
        probability_good = model.pipeline.predict_proba(frame)[:, 1]
    scores = np.clip(probability_good, 0.0, 1.0) * 1000.0
    return [
        ModelResponse(
            approved=bool(scores[index] >= APPROVAL_THRESHOLD),
            score=float(scores[index]),
        )
        for index in range(len(applicants))
    ]


def metrics_for(model_name: str) -> dict[str, Any]:
    return load_real_model(model_name).metrics
