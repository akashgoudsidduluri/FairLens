"""Evidence assembled from the committed evaluation results.

Nothing on the Evidence page is typed in by hand. This module reads
``eval/results/*.csv`` and ``real_models.md`` and computes the aggregates the
API serves. A missing file produces an empty section and a source marker; it
does not crash the service or invent a number.
"""

from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from config_loader import repo_path

DEFAULT_RESULTS_DIR = "eval/results"

_REAL_LABELS = {
    "adult_income": "UCI Adult Income",
    "uci_credit_default": "UCI Credit Default",
}

_FAIRLEARN_ATTRIBUTES = (
    ("sex", "sex"),
    ("age", "age"),
    ("race", "race"),
)


def results_directory(config: dict[str, Any] | None = None) -> Path:
    configured = ((config or {}).get("service") or {}).get("results_dir")
    return repo_path(configured or DEFAULT_RESULTS_DIR)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _integer(value: str | None) -> int | None:
    number = _number(value)
    return int(round(number)) if number is not None else None


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _unique(values: Iterable[str]) -> list[str]:
    seen: OrderedDict[str, None] = OrderedDict()
    for value in values:
        text = (value or "").strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


def _source(path: Path) -> dict[str, Any]:
    try:
        label = path.relative_to(repo_path(".")).as_posix()
    except ValueError:
        label = path.name
    return {"path": label, "present": path.exists()}


def _sandbox_models(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[int, list[dict[str, str]]] = OrderedDict()
    for row in rows:
        model_id = _integer(row.get("model_id"))
        if model_id is None:
            continue
        grouped.setdefault(model_id, []).append(row)

    models: list[dict[str, Any]] = []
    for model_id in sorted(grouped):
        runs = grouped[model_id]
        kept = [float(_integer(row.get("kept")) or 0) for row in runs]
        rejected = [float(_integer(row.get("rejected")) or 0) for row in runs]
        immaterial = [float(_integer(row.get("immaterial")) or 0) for row in runs]
        expectation_values = [
            row.get("expectation", "").strip().upper() for row in runs
        ]
        expectation_total = sum(
            1 for value in expectation_values if value in {"PASS", "MISS"}
        )
        expectation_passed = sum(1 for value in expectation_values if value == "PASS")

        before = [
            value
            for value in (_integer(row.get("false_alarm_before")) for row in runs)
            if value is not None
        ]
        after = [
            value
            for value in (_integer(row.get("false_alarm_after")) for row in runs)
            if value is not None
        ]
        false_alarm_runs = min(len(before), len(after))

        models.append(
            {
                "model_id": model_id,
                "runs": len(runs),
                "expectation_passed": expectation_passed,
                "expectation_total": expectation_total,
                "kept_mean": _mean(kept),
                "kept_min": int(min(kept)),
                "kept_max": int(max(kept)),
                "rejected_mean": _mean(rejected),
                "immaterial_mean": _mean(immaterial),
                "false_alarm_before": sum(before) if before else None,
                "false_alarm_after": sum(after) if after else None,
                "false_alarm_runs": false_alarm_runs,
                "runtime_mean_s": _mean(
                    [
                        value
                        for value in (_number(row.get("runtime_s")) for row in runs)
                        if value is not None
                    ]
                ),
                "number_check_passed": sum(
                    1
                    for row in runs
                    if (row.get("number_check_passed") or "").strip().lower()
                    == "true"
                ),
                "misses": _unique(row.get("misses", "") for row in runs),
            }
        )
    return models


def _fairlearn_metrics(row: dict[str, str]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for key, label in _FAIRLEARN_ATTRIBUTES:
        metrics.append(
            {
                "attribute": label,
                "demographic_parity_difference": _number(
                    row.get(f"fairlearn_{key}_demographic_parity_difference")
                ),
                "equalized_odds_difference": _number(
                    row.get(f"fairlearn_{key}_equalized_odds_difference")
                ),
            }
        )
    return metrics


def _real_models(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    for row in rows:
        name = (row.get("model") or "").strip()
        if name:
            grouped.setdefault(name, []).append(row)

    models: list[dict[str, Any]] = []
    for name, runs in grouped.items():
        kept = [float(_integer(row.get("kept")) or 0) for row in runs]
        rejected = [float(_integer(row.get("rejected")) or 0) for row in runs]
        immaterial = [float(_integer(row.get("immaterial")) or 0) for row in runs]
        impacts = [
            value
            for value in (_number(row.get("impact_per_10k")) for row in runs)
            if value is not None
        ]
        first = runs[0]
        supported = _unique(
            token
            for row in runs
            for token in (row.get("supported_probes") or "").split(";")
        )
        skipped = _unique(
            token
            for row in runs
            for token in (row.get("skipped_probes") or "").split(";")
        )
        notes = _unique(
            row.get(column, "")
            for row in runs
            for column in ("kept_details", "rejected_details", "immaterial_details")
        )
        models.append(
            {
                "model": name,
                "label": _REAL_LABELS.get(name, name.replace("_", " ").title()),
                "runs": len(runs),
                "supported_probes": supported,
                "skipped_probes": skipped,
                "kept_mean": _mean(kept),
                "rejected_mean": _mean(rejected),
                "immaterial_mean": _mean(immaterial),
                "impact_per_10k_mean": _mean(impacts) if impacts else None,
                "impact_per_10k_min": min(impacts) if impacts else None,
                "impact_per_10k_max": max(impacts) if impacts else None,
                "holdout_accuracy": _number(first.get("holdout_accuracy")),
                "holdout_auc": _number(first.get("holdout_auc")),
                "fairlearn": _fairlearn_metrics(first),
                "notes": notes,
                "errors": _unique(row.get("error", "") for row in runs),
            }
        )
    return models


_SUITE_B_MATERIALITY = 0.02


def _suite_b_models(
    rows: list[dict[str, str]], fairlearn_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Suite B rows at the pre-registered materiality, plus Fairlearn gaps.

    The 1%/3% sensitivity rows stay in ``suite_b.csv`` for the report but are
    never averaged into the headline table: the pre-registered materiality is 2%
    and the sensitivity is not a second chance to pick a better result.
    """

    grouped: OrderedDict[int, list[dict[str, str]]] = OrderedDict()
    for row in rows:
        if (row.get("suite") or "").strip().upper() != "B":
            continue
        materiality = _number(row.get("materiality"))
        if materiality is None or abs(materiality - _SUITE_B_MATERIALITY) > 1e-9:
            continue
        model_id = _integer(row.get("model_id"))
        if model_id is None:
            continue
        grouped.setdefault(model_id, []).append(row)

    gaps: dict[int, tuple[float, str]] = {}
    for row in fairlearn_rows:
        model_id = _integer(row.get("model_id"))
        gap = _number(row.get("dp_difference"))
        if model_id is None or gap is None:
            continue
        attribute = (row.get("attribute") or "").strip()
        if model_id not in gaps or gap > gaps[model_id][0]:
            gaps[model_id] = (gap, attribute)

    models: list[dict[str, Any]] = []
    for model_id in sorted(grouped):
        runs = grouped[model_id]
        kept = [float(_integer(row.get("kept")) or 0) for row in runs]
        candidates = [
            float(_integer(row.get("candidates")) or 0) for row in runs
        ]
        confirmed = [float(_integer(row.get("confirmed")) or 0) for row in runs]
        expectation_values = [
            row.get("expectation", "").strip().upper() for row in runs
        ]
        expectation_total = sum(
            1 for value in expectation_values if value in {"PASS", "MISS"}
        )
        expectation_passed = sum(1 for value in expectation_values if value == "PASS")
        before = [
            value
            for value in (_integer(row.get("false_alarm_before")) for row in runs)
            if value is not None
        ]
        after = [
            value
            for value in (_integer(row.get("false_alarm_after")) for row in runs)
            if value is not None
        ]
        mde200 = next(
            (
                value
                for value in (_number(row.get("mde_n200")) for row in runs)
                if value is not None
            ),
            None,
        )
        mde1000 = next(
            (
                value
                for value in (_number(row.get("mde_n1000")) for row in runs)
                if value is not None
            ),
            None,
        )
        gap, gap_attribute = gaps.get(model_id, (None, ""))
        models.append(
            {
                "model_id": model_id,
                "runs": len(runs),
                "expectation_passed": expectation_passed,
                "expectation_total": expectation_total,
                "kept_mean": _mean(kept),
                "kept_min": int(min(kept)),
                "kept_max": int(max(kept)),
                "candidates_mean": _mean(candidates),
                "confirmed_mean": _mean(confirmed),
                "cells_examined": int(
                    round(
                        _mean(
                            [
                                value
                                for value in (
                                    _integer(row.get("cells_examined")) for row in runs
                                )
                                if value is not None
                            ]
                        )
                    )
                ),
                "false_alarm_before": sum(before) if before else None,
                "false_alarm_after": sum(after) if after else None,
                "runtime_mean_s": _mean(
                    [
                        value
                        for value in (_number(row.get("runtime_s")) for row in runs)
                        if value is not None
                    ]
                ),
                "mde_n200": mde200,
                "mde_n1000": mde1000,
                "kept_ids": _unique(
                    identifier
                    for row in runs
                    for identifier in (row.get("kept_ids") or "").split(";")
                ),
                "misses": _unique(row.get("misses", "") for row in runs),
                "notes": _unique(row.get("notes", "") for row in runs),
                "dose_response": _unique(
                    row.get("dose_response", "") for row in runs
                ),
                "max_dp_gap": gap,
                "max_dp_attribute": gap_attribute,
            }
        )
    return models


def _suite_b_payload(root: Path, suffix: str = "") -> dict[str, Any]:
    """One suite B protocol, read from its own committed files.

    Protocol 1 has no suffix. Protocol 2 uses ``_r51``; both are returned
    independently so the Evidence page can show them side by side.
    """

    rows = _read_rows(root / f"suite_b{suffix}.csv")
    fairlearn_rows = _read_rows(root / f"suite_b{suffix}_fairlearn.csv")
    markdown = _read_text(root / f"suite_b{suffix}.md")
    models = _suite_b_models(rows, fairlearn_rows)
    return {
        "models": models,
        "runs": sum(model["runs"] for model in models),
        "expectation_passed": sum(
            model["expectation_passed"] for model in models
        ),
        "expectation_total": sum(model["expectation_total"] for model in models),
        "markdown": markdown,
        "sources": [
            _source(root / f"suite_b{suffix}.csv"),
            _source(root / f"suite_b{suffix}_fairlearn.csv"),
            _source(root / f"suite_b{suffix}.md"),
        ],
    }


def build_evidence(directory: Path | None = None) -> dict[str, Any]:
    root = directory or results_directory()
    sandbox_rows = _read_rows(root / "results.csv")
    real_rows = _read_rows(root / "real_models.csv")
    markdown = _read_text(root / "real_models.md")

    sandbox_models = _sandbox_models(sandbox_rows)
    real_models = _real_models(real_rows)
    suite_b = _suite_b_payload(root)
    suite_b_r51 = _suite_b_payload(root, "_r51")

    before_values = [
        model["false_alarm_before"]
        for model in sandbox_models
        if model["false_alarm_before"] is not None
    ]
    after_values = [
        model["false_alarm_after"]
        for model in sandbox_models
        if model["false_alarm_after"] is not None
    ]

    return {
        "sandbox": {
            "models": sandbox_models,
            "runs": len(sandbox_rows),
            "expectation_passed": sum(
                model["expectation_passed"] for model in sandbox_models
            ),
            "expectation_total": sum(
                model["expectation_total"] for model in sandbox_models
            ),
            "false_alarm_before": sum(before_values) if before_values else None,
            "false_alarm_after": sum(after_values) if after_values else None,
            "sources": [
                _source(root / "results.csv"),
                _source(root / "summary.md"),
            ],
        },
        "real": {
            "models": real_models,
            "markdown": markdown,
            "sources": [
                _source(root / "real_models.csv"),
                _source(root / "fairlearn.csv"),
                _source(root / "real_models.md"),
            ],
        },
        "suite_b": suite_b,
        "suite_b_r51": suite_b_r51,
    }
