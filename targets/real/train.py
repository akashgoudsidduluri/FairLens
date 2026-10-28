"""Train and persist the two real-data targets.

Run from the repository root:

    .venv\\Scripts\\python -m targets.real.train

Outputs (committed, so audits and tests are reproducible offline):

    data/real/artifacts/credit_logistic.joblib
    data/real/artifacts/credit_logistic.metrics.json
    data/real/artifacts/adult_gbm.joblib
    data/real/artifacts/adult_gbm.metrics.json

Choices fixed before any audit (see DECISIONS.md D-019):

- Fixed seed 42 for the split and the estimator.
- 80/20 stratified holdout.
- Logistic regression for credit default; histogram gradient boosting for Adult.
- The protected attribute ``sex`` is a natural feature. No "fairness-aware"
  variant is trained by default.
- Approval rule: probability of the favourable label >= 0.5, score = p*1000.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from config_loader import REPO_ROOT
from targets.real.datasets import dataset_sha256, dataset_summary, load_dataset
from targets.real.features import (
    ADULT_CATEGORICAL,
    ADULT_NUMERIC,
    CREDIT_FEATURES,
    UNUSED_FIELDS,
    USED_FIELDS,
)

ARTIFACT_DIR = REPO_ROOT / "data" / "real" / "artifacts"
SEED = 42
TEST_SIZE = 0.2
APPROVAL_THRESHOLD = 0.5

MODELS = {
    "uci_credit_default": {
        "artifact": "credit_logistic.joblib",
        "features": CREDIT_FEATURES,
        "label": "credit default next month (1 = default)",
        "favorable": "no default",
    },
    "adult_income": {
        "artifact": "adult_gbm.joblib",
        "features": ADULT_NUMERIC + ADULT_CATEGORICAL,
        "label": "income > 50K (1 = above 50K)",
        "favorable": "income > 50K",
    },
}


def _age_band(age: int) -> str:
    if age < 35:
        return "<35"
    if age <= 44:
        return "35-44"
    return "45+"


def _fairlearn_block(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive: pd.Series,
    label: str,
) -> dict[str, Any]:
    return {
        "attribute": label,
        "demographic_parity_difference": float(
            demographic_parity_difference(
                y_true=y_true, y_pred=y_pred, sensitive_features=sensitive
            )
        ),
        "equalized_odds_difference": float(
            equalized_odds_difference(
                y_true=y_true, y_pred=y_pred, sensitive_features=sensitive
            )
        ),
        "approval_rates": {
            str(group): float(rate)
            for group, rate in pd.DataFrame(
                {"group": sensitive, "approved": y_pred}
            )
            .groupby("group", observed=True)["approved"]
            .mean()
            .items()
        },
        "counts": {
            str(group): int(count)
            for group, count in sensitive.value_counts().items()
        },
    }


def _fit_credit(train: pd.DataFrame) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(max_iter=2000, solver="lbfgs", random_state=SEED),
            ),
        ]
    )


def _fit_adult(train: pd.DataFrame) -> Pipeline:
    preprocess = ColumnTransformer(
        [
            ("num", "passthrough", ADULT_NUMERIC),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ADULT_CATEGORICAL,
            ),
        ]
    )
    return Pipeline(
        [
            ("prep", preprocess),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_iter=200,
                    learning_rate=0.08,
                    max_leaf_nodes=31,
                    random_state=SEED,
                ),
            ),
        ]
    )


def _prob_good(model_name: str, pipeline: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    probability = pipeline.predict_proba(frame[MODELS[model_name]["features"]])[:, 1]
    if model_name == "uci_credit_default":
        # Class 1 is default; approval means "no default".
        return 1.0 - probability
    return probability


def _quantile_grids(frame: pd.DataFrame, columns: list[str]) -> dict[str, list[float]]:
    quantiles = np.linspace(0, 100, 101)
    return {
        column: [float(value) for value in np.percentile(frame[column], quantiles)]
        for column in columns
    }


def train_model(model_name: str, frame: pd.DataFrame) -> dict[str, Any]:
    specification = MODELS[model_name]
    features = specification["features"]
    train, holdout = train_test_split(
        frame,
        test_size=TEST_SIZE,
        random_state=SEED,
        stratify=frame["target"],
    )
    pipeline = (
        _fit_credit(train) if model_name == "uci_credit_default" else _fit_adult(train)
    )
    pipeline.fit(train[features], train["target"])

    probability_good = _prob_good(model_name, pipeline, holdout)
    approved = probability_good >= APPROVAL_THRESHOLD
    y_true = holdout["target"].to_numpy()
    y_true_good = (
        (1 - y_true) if model_name == "uci_credit_default" else y_true
    )

    numeric = [
        column
        for column in features
        if pd.api.types.is_numeric_dtype(frame[column])
    ]
    categorical = [column for column in features if column not in numeric]

    sensitive_frames = {
        "sex": holdout["sex"].map({1: "male", 2: "female"})
        if model_name == "uci_credit_default"
        else holdout["sex"],
        "age_band": holdout["age"].map(_age_band),
    }
    if model_name == "adult_income":
        sensitive_frames["race"] = holdout["race"]

    fairness = {
        name: _fairlearn_block(
            y_true_good, approved, values.reset_index(drop=True), name
        )
        for name, values in sensitive_frames.items()
    }

    metrics = {
        "model": model_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "test_size": TEST_SIZE,
        "rows_total": int(len(frame)),
        "rows_train": int(len(train)),
        "rows_holdout": int(len(holdout)),
        "features": features,
        "protected_attribute_in_features": "sex" in features,
        "label": specification["label"],
        "favorable_outcome": specification["favorable"],
        "approval_rule": f"P(favourable) >= {APPROVAL_THRESHOLD}; score = P*1000",
        "holdout": {
            "accuracy": float(accuracy_score(y_true_good, approved)),
            "roc_auc": float(roc_auc_score(y_true_good, probability_good)),
            "approval_rate": float(approved.mean()),
            "positive_rate": float(np.mean(y_true_good)),
        },
        "fairlearn_holdout": fairness,
        "quantile_grids": _quantile_grids(train, numeric),
        "ranges": {
            column: [float(train[column].min()), float(train[column].max())]
            for column in numeric
        },
        "categories": {
            column: sorted(train[column].astype(str).unique().tolist())
            for column in categorical
        },
        "used_canonical_fields": USED_FIELDS[model_name],
        "unused_canonical_fields": UNUSED_FIELDS[model_name],
        "dataset": dataset_summary(model_name),
        "dataset_sha256": dataset_sha256(model_name),
        "artifact": specification["artifact"],
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ARTIFACT_DIR / specification["artifact"])
    metrics_path = ARTIFACT_DIR / f"{model_name}.metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        choices=sorted(MODELS) + ["all"],
        default="all",
        help="Which model to train",
    )
    args = parser.parse_args(argv)
    names = sorted(MODELS) if args.model == "all" else [args.model]
    for name in names:
        frame = load_dataset(name)
        metrics = train_model(name, frame)
        holdout = metrics["holdout"]
        print(
            f"{name}: rows={metrics['rows_total']} "
            f"accuracy={holdout['accuracy']:.4f} auc={holdout['roc_auc']:.4f} "
            f"approval={holdout['approval_rate']:.3f}"
        )
        for attribute, block in metrics["fairlearn_holdout"].items():
            print(
                f"  {attribute}: DP={block['demographic_parity_difference']:.4f} "
                f"EO={block['equalized_odds_difference']:.4f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
