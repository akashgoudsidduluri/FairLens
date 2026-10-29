"""Suite B evaluation (R5 Step 7): models 8-15, control B, suite A rerun.

Run from the repository root:

    .venv\\Scripts\\python -m eval.run_suite_b

This is the pre-registered evaluation written in ``expected_findings.md`` under
"Suite B and generalized search". It does not change any threshold, penalty, bin,
panel cell, or seed. The 1%/3% sensitivity copies the config in memory.

Outputs:

- ``eval/results/suite_b.csv`` - every audit (suite B main and sensitivity,
  suite A rerun with the generalized protocol).
- ``eval/results/suite_b_fairlearn.csv`` - Fairlearn observational baseline on
  the same 4,000 synthetic applicants for models 8-15.
- ``eval/results/suite_b.md`` - expected vs found, misses, false alarms before
  and after the Skeptic, cells, candidates, confirmed cells, MDE, runtime, the
  materiality sensitivity, the suite A new-vs-old comparison, and the Fairlearn
  comparison.
"""

from __future__ import annotations

import argparse
import csv
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)

from auditor.pipeline import collect_audit
from auditor.prober import Prober
from config_loader import REPO_ROOT, load_config, with_overrides
from eval.sandbox_runner import start_servers, stop_servers
from sandbox.generator import generate_applicants, generate_segment, make_twin

RESULTS = REPO_ROOT / "eval" / "results"
SUITE_A = tuple(range(1, 8))
SUITE_B = tuple(range(8, 16))
CLEAN_B = {14, 15}
LEGITIMATE_TREATMENTS = {
    "income",
    "credit_score",
    "loan_amount",
    "employment_years",
}
MATERIALITIES = (0.01, 0.03)
# Pre-registered pass criteria ask for an age dose-response series (Models 8 and
# 13). These are reporting probes, not a search: fixed points and sample size.
DIAGNOSTIC_AGES = (45, 50, 55, 60)
DIAGNOSTIC_PAIRS = 500
FAIRLEARN_ATTRIBUTES = [
    "gender",
    "age_band",
    "pincode_group",
    "name_group",
    "urban_rural",
]


# ------------------------------------------------------------------ audit task
def _finding_row(finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "kind": finding.kind,
        "status": finding.status,
        "attribute_or_subgroup": finding.attribute_or_subgroup,
        "target_group": finding.target_group,
        "comparison_group": finding.comparison_group,
        "treatment": finding.treatment,
        "treatment_level": finding.treatment_level,
        "context": dict(finding.context or {}),
        "n": finding.evidence.n,
        "b": finding.evidence.b,
        "c": finding.evidence.c,
        "net_flip_rate": finding.evidence.net_flip_rate,
        "p_adjusted": finding.evidence.p_adjusted,
        "observational_gap": finding.observational_gap,
        "reason": finding.reason or "",
        "merged_into": finding.merged_into,
    }


def _age_dose_response(
    api_url: str, config: dict[str, Any], model_id: int, seed: int
) -> dict[str, Any]:
    """Fixed-age twin probes for the pre-registered age pass criteria.

    Originals are the ``<35`` band; each point moves every original to one exact
    age while holding income, loan amount, credit, employment, gender, pincode,
    and name fixed. This is the same counterfactual as the band twins, just at a
    finer age resolution. It is reported as a diagnostic, not used to select or
    reject any finding.
    """

    prober = Prober(api_url, config)
    originals, _ = generate_segment(
        DIAGNOSTIC_PAIRS, seed=seed + 81_000, age_band="<35"
    )
    rows: list[dict[str, Any]] = []
    used = 0
    for index, age in enumerate(DIAGNOSTIC_AGES):
        rng = np.random.default_rng(seed + 83_000 + index)
        left, right = [], []
        for original in originals:
            try:
                twin = make_twin(original, "age", int(age), rng)
            except ValueError:
                continue
            left.append(original)
            right.append(twin)
        if not left:
            continue
        left_responses = prober.score_many_sync(model_id, left)
        right_responses = prober.score_many_sync(model_id, right)
        b = sum(
            1
            for original, twin in zip(left_responses, right_responses)
            if original.approved and not twin.approved
        )
        c = sum(
            1
            for original, twin in zip(left_responses, right_responses)
            if not original.approved and twin.approved
        )
        used += len(left) + len(right)
        rows.append(
            {
                "age": age,
                "n": len(left),
                "b": b,
                "c": c,
                "net_flip_rate": (b - c) / len(left),
            }
        )
    return {"points": rows, "applicants": used, "seed": seed + 81_000}


def _subgroup(finding: dict[str, Any]) -> dict[str, str]:
    group = {str(finding.get("treatment")): str(finding.get("treatment_level"))}
    group.update(finding.get("context") or {})
    return group


def _cell(
    search: dict[str, Any], treatment: str, level: str, context: dict[str, str] | None
) -> dict[str, Any] | None:
    wanted = context or {}
    for row in search.get("discovery_results", []):
        if (
            row["treatment"] == treatment
            and row["level"] == level
            and row["context"] == wanted
        ):
            return row
    return None


def _covered(group: dict[str, str], **wanted: str) -> bool:
    return all(group.get(key) == value for key, value in wanted.items())


def _suite_b_expectation(
    model_id: int,
    findings: list[dict[str, Any]],
    search: dict[str, Any],
    observational: dict[str, Any],
    diagnostic: dict[str, Any] | None,
    materiality: float,
) -> tuple[str, list[str], list[str]]:
    """Pre-registered pass criteria for suite B (expected_findings.md)."""

    kept = [finding for finding in findings if finding["status"] == "kept"]
    misses: list[str] = []
    notes: list[str] = []
    kept_ids = sorted(finding["id"] for finding in kept)

    for finding in kept:
        if str(finding.get("treatment")) in LEGITIMATE_TREATMENTS:
            misses.append(
                f"kept a legitimate attribute as treatment: {finding['id']}"
            )

    if model_id in {8, 13}:
        age_kept = [
            finding
            for finding in kept
            if finding["treatment"] == "age" and finding["treatment_level"] == "45+"
        ]
        if len(kept) != 1:
            misses.append(f"expected exactly one kept finding, got {len(kept)}")
        if not age_kept:
            misses.append("kept age finding at level 45+ is missing")
        elif age_kept[0]["context"]:
            notes.append(
                "kept age finding is context-specific, not the pre-registered "
                f"main effect: {age_kept[0]['id']} context={age_kept[0]['context']}"
            )

    if model_id == 8:
        below = [
            point
            for point in (diagnostic or {}).get("points", [])
            if point["age"] < 55
        ]
        above = [
            point
            for point in (diagnostic or {}).get("points", [])
            if point["age"] >= 55
        ]
        if not below or not above:
            misses.append("age dose-response diagnostic missing")
        else:
            worst_below = max(abs(point["net_flip_rate"]) for point in below)
            best_above = max(point["net_flip_rate"] for point in above)
            if worst_below >= materiality:
                misses.append(
                    "net below 55 is not near zero "
                    f"(max |net|={worst_below:.4f} >= {materiality:.2f})"
                )
            if best_above < materiality:
                misses.append(
                    "net at 55+ is not material "
                    f"(max net={best_above:.4f} < {materiality:.2f})"
                )

    elif model_id == 9:
        if len(kept) != 1:
            misses.append(f"expected exactly one kept finding, got {len(kept)}")
        if not any(
            _covered(_subgroup(finding), pincode_group="P2", gender="female")
            for finding in kept
        ):
            misses.append("kept finding does not name both pincode P2 and female")

    elif model_id == 10:
        if len(kept) != 1:
            misses.append(f"expected exactly one kept finding, got {len(kept)}")
        if not any(
            _covered(_subgroup(finding), name_group="N2", age="45+")
            for finding in kept
        ):
            misses.append("kept finding does not name both name N2 and age 45+")
        if any(
            finding["treatment"] == "name_group" and not finding["context"]
            for finding in kept
        ):
            misses.append("a name main effect was kept on its own")

    elif model_id == 11:
        if len(kept) != 1:
            misses.append(f"expected exactly one kept finding, got {len(kept)}")
        if not any(
            finding["treatment"] == "pincode_group"
            and finding["treatment_level"] == "P2"
            and finding["context"].get("loan_amount") == "high"
            for finding in kept
        ):
            misses.append("kept pincode P2 finding in the high-loan context is missing")
        if any(finding["context"].get("loan_amount") == "low" for finding in kept):
            misses.append("a low-loan cell was kept")

    elif model_id == 12:
        if len(kept) != 1:
            misses.append(f"expected exactly one kept finding, got {len(kept)}")
        if not any(
            _covered(
                _subgroup(finding),
                gender="female",
                age="45+",
                urban_rural="rural",
                name_group="N2",
            )
            for finding in kept
        ):
            misses.append(
                "kept finding does not name gender/age/rural/name together"
            )

    elif model_id == 13:
        younger = _cell(search, "age", "35-44", {})
        older = _cell(search, "age", "45+", {})
        if younger is None or older is None:
            misses.append("age main-effect cells missing from the discovery panel")
        elif older["net_flip_rate"] - younger["net_flip_rate"] < 0.05:
            misses.append(
                "age 45+ net does not exceed age 35-44 net by 0.05 "
                f"({older['net_flip_rate']:+.4f} vs {younger['net_flip_rate']:+.4f})"
            )
        if not (diagnostic or {}).get("points"):
            misses.append("age dose-response series missing")

    elif model_id == 14:
        if kept:
            misses.append(f"expected no kept findings, got {kept_ids}")
        rejected = [finding for finding in findings if finding["status"] == "rejected"]
        if not any(
            "loan_amount" in finding["reason"].lower()
            or "loan amount" in finding["reason"].lower()
            for finding in rejected
        ):
            misses.append(
                "no rejected candidate cites loan amount (the pre-registered "
                "explanation path is unreachable when no candidate reaches the "
                "Skeptic)"
            )
        gaps = observational.get("gaps") or {}
        if not any(
            float(gap.get("gap", 0.0)) >= materiality for gap in gaps.values()
        ):
            misses.append("no material observational gap was reported")

    elif model_id == 15:
        if kept:
            misses.append(f"expected no kept findings, got {kept_ids}")

    return ("PASS" if not misses else "MISS"), misses, notes


def _suite_a_expectation(
    model_id: int,
    findings: list[dict[str, Any]],
    observational: dict[str, Any],
    materiality: float,
) -> tuple[str, list[str], list[str]]:
    """Semantic re-check of the frozen suite A expectations, new protocol.

    The frozen ``expectation_check`` keys off ``single-*``/``inter-*`` ids, which
    the generalized protocol does not produce. This applies the same meaning to
    the generalized finding descriptions. The old-protocol numbers are never
    replaced; they are read from ``eval/results/results.csv``.
    """

    kept = [finding for finding in findings if finding["status"] == "kept"]
    misses: list[str] = []
    notes: list[str] = []
    kept_ids = sorted(finding["id"] for finding in kept)

    for finding in kept:
        if str(finding.get("treatment")) in LEGITIMATE_TREATMENTS:
            misses.append(
                f"kept a legitimate attribute as treatment: {finding['id']}"
            )

    def has_treatment(attribute: str, level: str | None = None) -> bool:
        return any(
            finding["treatment"] == attribute
            and (level is None or finding["treatment_level"] == level)
            for finding in kept
        )

    if model_id in {1, 6}:
        if kept:
            misses.append(f"expected no kept findings, got {kept_ids}")
    elif model_id == 2:
        if not has_treatment("gender", "female"):
            misses.append("gender female finding not kept")
        if has_treatment("pincode_group") or has_treatment("name_group"):
            misses.append("unexpected pincode/name treatment kept")
    elif model_id == 3:
        if not has_treatment("pincode_group", "P2"):
            misses.append("pincode P2 finding not kept")
        if has_treatment("gender"):
            misses.append("gender finding unexpectedly kept")
    elif model_id == 4:
        if not has_treatment("name_group", "N2"):
            misses.append("name N2 finding not kept")
        if has_treatment("gender"):
            misses.append("gender finding unexpectedly kept")
    elif model_id == 5:
        hotspot = [
            finding
            for finding in kept
            if _covered(
                _subgroup(finding),
                gender="female",
                age="45+",
                urban_rural="rural",
            )
        ]
        if not hotspot:
            misses.append("female/45+/rural hotspot not kept")
        if any(
            finding["treatment"] == "gender" and not finding["context"]
            for finding in kept
        ):
            misses.append("single-attribute gender main effect was kept")
    elif model_id == 7:
        if kept:
            misses.append(f"confounded model had kept findings: {kept_ids}")
        gaps = observational.get("gaps") or {}
        if not any(
            float(gap.get("gap", 0.0)) >= materiality for gap in gaps.values()
        ):
            misses.append("no material observational gap found")

    return ("PASS" if not misses else "MISS"), misses, notes


def _prefiltered(findings: list[dict[str, Any]], alpha: float, materiality: float) -> int:
    return sum(
        1
        for finding in findings
        if finding["n"] > 0
        and finding["p_adjusted"] < alpha
        and finding["net_flip_rate"] >= materiality
    )


def _audit_task(task: dict[str, Any]) -> dict[str, Any]:
    """Worker process: one generalized audit plus its age diagnostic."""

    config = load_config()
    config["audit"]["search"]["enabled"] = True
    materiality = float(task["materiality"])
    if materiality != float(config["audit"]["materiality"]):
        config = with_overrides(config, {"audit.materiality": materiality})
    alpha = float(config["audit"]["alpha"])
    started = time.perf_counter()
    model_id = int(task["model_id"])
    seed = int(task["seed"])
    suite = str(task["suite"])
    try:
        _, report = collect_audit(
            model_id,
            str(task["api_url"]),
            config,
            seed=seed,
            include_mitigation=False,
            include_narrative=False,
        )
        seconds = time.perf_counter() - started
        search = report.observational.get("search") or {}
        observational = report.observational
        findings = [_finding_row(finding) for finding in report.findings]
        kept = [finding for finding in findings if finding["status"] == "kept"]
        rejected = [f for f in findings if f["status"] == "rejected"]
        immaterial = [f for f in findings if f["status"] == "immaterial"]
        merged = [f for f in findings if f["status"] == "merged"]
        diagnostic = (
            _age_dose_response(str(task["api_url"]), config, model_id, seed)
            if model_id in {8, 13}
            else None
        )
        if suite == "B":
            expectation, misses, notes = _suite_b_expectation(
                model_id, findings, search, observational, diagnostic, materiality
            )
        else:
            expectation, misses, notes = _suite_a_expectation(
                model_id, findings, observational, materiality
            )
        mde = {int(row["n"]): row["mde"] for row in search.get("mde_by_cell_size", [])}
        plan = search.get("plan") or {}
        return {
            "suite": suite,
            "model_id": model_id,
            "seed": seed,
            "materiality": materiality,
            "runtime_s": round(seconds, 2),
            "cells_examined": int(search.get("cells_examined", 0)),
            "cells_tested": int(search.get("cells_tested", 0)),
            "discovery_pairs": int(search.get("phase_a_pairs", 0)),
            "confirmation_pairs": int(search.get("phase_b_pairs", 0)),
            "candidates": len(search.get("candidates", [])),
            "confirmed": len(search.get("confirmed", [])),
            "kept": len(kept),
            "rejected": len(rejected),
            "immaterial": len(immaterial),
            "merged": len(merged),
            "kept_ids": [finding["id"] for finding in kept],
            "kept_findings": kept,
            "expectation": expectation,
            "misses": misses,
            "notes": notes,
            "false_alarm_before": _prefiltered(findings, alpha, materiality),
            "false_alarm_after": len(kept),
            "observational_gaps": {
                attribute: float(gap.get("gap", 0.0))
                for attribute, gap in (observational.get("gaps") or {}).items()
            },
            "planned_applicants": int(plan.get("planned_applicants", 0)),
            "probe_cap": int(plan.get("probe_cap", 0)),
            "diagnostic_applicants": int((diagnostic or {}).get("applicants", 0)),
            "mde_n200": mde.get(200),
            "mde_n1000": mde.get(1000),
            "dose_response": (diagnostic or {}).get("points", []),
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "suite": suite,
            "model_id": model_id,
            "seed": seed,
            "materiality": materiality,
            "runtime_s": round(time.perf_counter() - started, 2),
            "cells_examined": 0,
            "cells_tested": 0,
            "discovery_pairs": 0,
            "confirmation_pairs": 0,
            "candidates": 0,
            "confirmed": 0,
            "kept": 0,
            "rejected": 0,
            "immaterial": 0,
            "merged": 0,
            "kept_ids": [],
            "kept_findings": [],
            "expectation": "ERROR",
            "misses": [f"{type(exc).__name__}: {exc}"],
            "notes": [],
            "false_alarm_before": 0,
            "false_alarm_after": 0,
            "observational_gaps": {},
            "planned_applicants": 0,
            "probe_cap": 0,
            "diagnostic_applicants": 0,
            "mde_n200": None,
            "mde_n1000": None,
            "dose_response": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


# -------------------------------------------------------------------- fairlearn
def _metric(value: Any) -> float | str:
    if value is None:
        return ""
    number = float(value)
    return "" if not np.isfinite(number) else round(number, 4)


def _fairlearn(api_url: str, n: int, seed: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Observational DP/EO gaps for models 8-15 on one shared sample."""

    applicants, labels = generate_applicants(n, seed=seed)
    prober = Prober(api_url, config)
    rows: list[dict[str, Any]] = []
    for model_id in SUITE_B:
        responses = prober.score_many_sync(model_id, applicants)
        approved = np.array([response.approved for response in responses], dtype=bool)
        truth = np.array(labels, dtype=bool)
        for attribute in FAIRLEARN_ATTRIBUTES:
            sensitive = pd.Series(
                [getattr(applicant, attribute) for applicant in applicants]
            )
            dp = _metric(
                demographic_parity_difference(
                    y_true=truth, y_pred=approved, sensitive_features=sensitive
                )
            )
            eo = _metric(
                equalized_odds_difference(
                    y_true=truth, y_pred=approved, sensitive_features=sensitive
                )
            )
            rates = (
                pd.DataFrame({"group": sensitive, "approved": approved})
                .groupby("group", observed=True)["approved"]
                .mean()
                .round(4)
                .to_dict()
            )
            rows.append(
                {
                    "model_id": model_id,
                    "attribute": attribute,
                    "n": n,
                    "dp_difference": dp,
                    "eo_difference": eo,
                    "approval_rates": "; ".join(
                        f"{group}={rate:.4f}" for group, rate in sorted(rates.items())
                    ),
                }
            )
    return rows


# ---------------------------------------------------------------------- outputs
CSV_FIELDS = [
    "suite",
    "model_id",
    "seed",
    "materiality",
    "runtime_s",
    "cells_examined",
    "cells_tested",
    "discovery_pairs",
    "confirmation_pairs",
    "candidates",
    "confirmed",
    "kept",
    "rejected",
    "immaterial",
    "merged",
    "kept_ids",
    "expectation",
    "misses",
    "notes",
    "false_alarm_before",
    "false_alarm_after",
    "mde_n200",
    "mde_n1000",
    "planned_applicants",
    "diagnostic_applicants",
    "probe_cap",
    "dose_response",
    "error",
]


def _write_csv(rows: list[dict[str, Any]]) -> Path:
    path = RESULTS / "suite_b.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in sorted(
            rows, key=lambda item: (item["suite"], item["model_id"], item["materiality"], item["seed"])
        ):
            writer.writerow(
                {
                    **{field: row.get(field, "") for field in CSV_FIELDS},
                    "kept_ids": ";".join(row["kept_ids"]),
                    "misses": "; ".join(row["misses"]),
                    "notes": "; ".join(row["notes"]),
                    "dose_response": "; ".join(
                        f"{point['age']}:{point['net_flip_rate']:+.4f}"
                        for point in row["dose_response"]
                    ),
                }
            )
    return path


def _write_fairlearn_csv(rows: list[dict[str, Any]]) -> Path:
    path = RESULTS / "suite_b_fairlearn.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _kept_summary(rows: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        for identifier in row["kept_ids"]:
            counts[identifier] = counts.get(identifier, 0) + 1
    if not counts:
        return "none"
    return "; ".join(
        f"{identifier} x{count}"
        for identifier, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def _old_protocol() -> dict[int, dict[str, Any]]:
    path = RESULTS / "results.csv"
    if not path.exists():
        return {}
    summary: dict[int, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            model_id = int(row["model_id"])
            if abs(float(row["materiality"]) - 0.02) > 1e-9:
                continue
            entry = summary.setdefault(
                model_id, {"kept": [], "ids": set(), "pass": 0, "runs": 0}
            )
            entry["kept"].append(int(row["kept"]))
            entry["runs"] += 1
            entry["pass"] += 1 if row["expectation"] == "PASS" else 0
            for identifier in (row["kept_ids"] or "").split(";"):
                if identifier:
                    entry["ids"].add(identifier)
    for entry in summary.values():
        values = entry["kept"]
        entry["mean"] = float(np.mean(values)) if values else 0.0
        entry["range"] = f"{min(values)}-{max(values)}" if values else "0-0"
        entry["ids"] = sorted(entry["ids"])
    return summary


def _write_markdown(
    rows: list[dict[str, Any]],
    fairlearn_rows: list[dict[str, Any]],
    fairlearn_seed: int,
    fairlearn_n: int,
    started_at: str,
) -> Path:
    suite_b_main = [
        row
        for row in rows
        if row["suite"] == "B" and abs(row["materiality"] - 0.02) < 1e-9
    ]
    suite_b_sensitivity = [
        row
        for row in rows
        if row["suite"] == "B" and abs(row["materiality"] - 0.02) >= 1e-9
    ]
    suite_a_main = [
        row
        for row in rows
        if row["suite"] == "A" and abs(row["materiality"] - 0.02) < 1e-9
    ]
    errors = [row for row in rows if row["error"]]
    old = _old_protocol()

    main_effect_models = {8: "age", 13: "age"}
    merge_cases = [
        (row["model_id"], row["seed"], finding["id"])
        for row in suite_b_main
        for finding in row.get("kept_findings", [])
        if row["model_id"] in main_effect_models
        and finding.get("treatment") == main_effect_models[row["model_id"]]
        and finding.get("context")
    ]
    if merge_cases:
        model_id, seed, identifier = merge_cases[0]
        merge_limitation = (
            "- The merge rule can prefer a materially stronger context over the "
            f"pre-registered main effect. It did so in {len(merge_cases)} kept "
            f"finding(s); for example model {model_id} seed {seed} kept "
            f"`{identifier}` rather than the bare main effect. The choice is "
            "reported, not retuned."
        )
    else:
        merge_limitation = (
            "- The merge rule can prefer a materially stronger context over the "
            "pre-registered main effect when both survive the Skeptic. No such case "
            "occurred in this run."
        )

    multi_kept = [row for row in suite_b_main if row["kept"] > 1]
    if multi_kept:
        seeds_by_model: dict[int, list[int]] = {}
        for row in multi_kept:
            seeds_by_model.setdefault(row["model_id"], []).append(int(row["seed"]))
        parts = [
            f"model {model_id} seeds {', '.join(str(seed) for seed in sorted(seeds))}"
            for model_id, seeds in sorted(seeds_by_model.items())
        ]
        sibling_limitation = (
            "- The merge rule only folds a kept subgroup into a kept subgroup that "
            "contains it. Sibling contexts beneath the same main effect are not "
            f"folded together, so {'; '.join(parts)} kept more than one finding. "
            "The extra cells name the same treatment level in different contexts, "
            "not a new treatment; they are why the pre-registered \"exactly one "
            "kept finding\" criterion fails for those seeds."
        )
    else:
        sibling_limitation = (
            "- Sibling contexts beneath the same main effect are not folded "
            "together; no audit kept more than one finding in this run."
        )

    model_11 = [row for row in suite_b_main if row["model_id"] == 11]
    kept_11 = sorted(
        {identifier for row in model_11 for identifier in row["kept_ids"]}
    )
    loan_11 = any("loan_amount-high" in identifier for identifier in kept_11)
    model_11_limitation = ""
    if model_11 and kept_11 and not loan_11:
        model_11_limitation = (
            "- Model 11's planted `loan_amount=high` context is not in any kept "
            f"finding; the kept cell was `{kept_11[0]}` on every seed. Discovery "
            "ranked the high-income context above the pre-registered high-loan "
            "context and the merge kept that one. This is reported as a miss, not "
            "retuned."
        )

    slow = [row for row in rows if row["runtime_s"] and float(row["runtime_s"]) > 600]
    if slow:
        values = sorted(float(row["runtime_s"]) for row in slow)
        runtime_limitation = (
            "- A few batches report very long wall-clock times "
            f"({values[0]:.0f}-{values[-1]:.0f}s) with nearly identical values "
            "across the four concurrent workers, which is host suspension and "
            "scheduling time rather than audit compute. Probe counts, seeds, and "
            "statistics are unaffected, and runtime is not a benchmark."
        )
    else:
        runtime_limitation = (
            "- Runtimes are parallel worker wall-clock times, not a single-user "
            "benchmark, and include the pre-registered age diagnostic for Models 8 "
            "and 13."
        )

    lines = [
        "# Suite B and the generalized protocol (R5 Step 7)",
        "",
        f"Generated: {started_at}",
        "",
        "Pre-registered run from `expected_findings.md`: **models 8-14 plus clean "
        "control B (Model 15) x seeds 1-5** at the frozen materiality 2%, alpha "
        "0.05, Holm across every discovery cell, 80:20 discovery/confirmation. "
        "Models 1-7 (suite A) are rerun with the generalized protocol and shown "
        "next to their frozen old-protocol facts; the old numbers are not "
        "replaced or retuned. The 1%/3% sensitivity reuses the same seeds and "
        "statistics with an in-memory materiality override.",
        "",
        "A miss is any planted model whose expected treatment/context is not in "
        "the kept findings, a kept legitimate attribute as treatment, or a kept "
        "finding in Model 14/15. A false alarm before the Skeptic is a candidate "
        "cell (confirmed or over the confirmation budget) that is Holm-significant "
        "with net flip >= materiality; after the Skeptic it is a kept finding.",
        "",
        "## Suite B: expected vs found (5 seeds, 2%)",
        "",
        "| Model | Expected treatment / context | Kept mean (range) | PASS | Kept findings | "
        "False alarms before -> after | Cells | Candidates | Confirmed | MDE n=200 | MDE n=1000 | Mean runtime |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    expected = {
        8: "age `45+` / main effect",
        9: "pincode P2 or gender female / the other attribute",
        10: "name N2 or age `45+` / the other attribute",
        11: "pincode P2 / `loan_amount=high`",
        12: "gender female or age `45+` / 45+, rural, N2",
        13: "age main effect, graded",
        14: "no kept group finding",
        15: "no kept findings (control B)",
    }
    for model_id in SUITE_B:
        subset = [row for row in suite_b_main if row["model_id"] == model_id]
        if not subset:
            continue
        kept_values = [row["kept"] for row in subset]
        passes = sum(row["expectation"] == "PASS" for row in subset)
        before = sum(row["false_alarm_before"] for row in subset)
        after = sum(row["false_alarm_after"] for row in subset)
        cells = int(np.mean([row["cells_examined"] for row in subset]))
        candidates = int(np.mean([row["candidates"] for row in subset]))
        confirmed = int(np.mean([row["confirmed"] for row in subset]))
        mde200 = next((row["mde_n200"] for row in subset if row["mde_n200"] is not None), None)
        mde1000 = next((row["mde_n1000"] for row in subset if row["mde_n1000"] is not None), None)
        runtime = float(np.mean([row["runtime_s"] for row in subset]))
        lines.append(
            f"| {model_id} | {expected[model_id]} | "
            f"{np.mean(kept_values):.1f} ({min(kept_values)}-{max(kept_values)}) | "
            f"{passes}/{len(subset)} | {_kept_summary(subset)} | {before} -> {after} | "
            f"{cells} | {candidates} | {confirmed} | "
            f"{'' if mde200 is None else f'{mde200:.3f}'} | "
            f"{'' if mde1000 is None else f'{mde1000:.3f}'} | {runtime:.1f}s |"
        )

    lines.extend(["", "## Per-seed detail", "", "| Model | Seed | Kept | Kept ids | Expectation | Misses | Notes | Runtime |", "|---|---|---|---|---|---|---|---|"])
    for row in sorted(suite_b_main, key=lambda item: (item["model_id"], item["seed"])):
        lines.append(
            f"| {row['model_id']} | {row['seed']} | {row['kept']} | "
            f"{', '.join(row['kept_ids']) or 'none'} | {row['expectation']} | "
            f"{'; '.join(row['misses']) or 'none'} | {'; '.join(row['notes']) or 'none'} | "
            f"{row['runtime_s']:.1f}s |"
        )

    lines.extend(["", "## Misses and notes across all seeds", ""])
    miss_counts: dict[str, int] = {}
    note_counts: dict[str, int] = {}
    for row in suite_b_main:
        for miss in row["misses"]:
            miss_counts[miss] = miss_counts.get(miss, 0) + 1
        for note in row["notes"]:
            note_counts[note] = note_counts.get(note, 0) + 1
    if miss_counts:
        for miss, count in sorted(miss_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- **MISS x{count}**: {miss}")
    else:
        lines.append("- No misses.")
    if note_counts:
        for note, count in sorted(note_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- Note x{count}: {note}")

    false_alarms = [
        row for row in suite_b_main if row["model_id"] in CLEAN_B
    ]
    lines.extend(
        [
            "",
            "## False alarms before and after the Skeptic (Models 14 and 15)",
            "",
            "| Model | Seed | Kept | Confirmed cells | Before Skeptic | After Skeptic | Runtime |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in sorted(false_alarms, key=lambda item: (item["model_id"], item["seed"])):
        lines.append(
            f"| {row['model_id']} | {row['seed']} | {row['kept']} | {row['confirmed']} | "
            f"{row['false_alarm_before']} | {row['false_alarm_after']} | {row['runtime_s']:.1f}s |"
        )

    lines.extend(
        [
            "",
            "## Age dose-response (diagnostic reported for Models 8 and 13)",
            "",
            "Originals are the `<35` band; each point flips the age of the same "
            "applicant to one exact age, holding every other signal fixed. "
            "`500` pairs per point, fixed before the run. These probes are not "
            "used to select findings.",
            "",
            "| Model | Seed | " + " | ".join(f"age {age} net" for age in DIAGNOSTIC_AGES) + " |",
            "|---|---|" + "---|" * len(DIAGNOSTIC_AGES),
        ]
    )
    for row in sorted(
        [item for item in suite_b_main if item["model_id"] in {8, 13}],
        key=lambda item: (item["model_id"], item["seed"]),
    ):
        values = {point["age"]: point["net_flip_rate"] for point in row["dose_response"]}
        lines.append(
            f"| {row['model_id']} | {row['seed']} | "
            + " | ".join(
                f"{values.get(age, float('nan')):+.4f}" if age in values else "-"
                for age in DIAGNOSTIC_AGES
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Materiality sensitivity (in-memory override, same seeds)",
            "",
            "| Model | Kept mean 1% | Kept mean 2% | Kept mean 3% | PASS 1% | PASS 2% | PASS 3% |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for model_id in SUITE_B:
        cells = []
        for materiality in (0.01, 0.02, 0.03):
            source = suite_b_main if materiality == 0.02 else [
                row
                for row in suite_b_sensitivity
                if row["model_id"] == model_id
                and abs(row["materiality"] - materiality) < 1e-9
            ]
            subset = [row for row in source if row["model_id"] == model_id]
            cells.append(subset)
        means = [
            f"{float(np.mean([row['kept'] for row in subset])):.1f}"
            if subset
            else "n/a"
            for subset in cells
        ]
        passes = [
            f"{sum(row['expectation'] == 'PASS' for row in subset)}/{len(subset)}"
            if subset
            else "n/a"
            for subset in cells
        ]
        lines.append(f"| {model_id} | " + " | ".join(means + passes) + " |")

    lines.extend(
        [
            "",
            "The pre-registered materiality is 2%; 1% and 3% are sensitivity runs "
            "and are never used to pick the best result.",
            "",
            "## Suite A rerun under the generalized protocol",
            "",
            "Old-protocol facts are read from `eval/results/results.csv` (seven "
            "models x five seeds). They are frozen and never replaced. The new "
            "protocol is checked semantically because it no longer emits "
            "`single-*`/`inter-*` findings.",
            "",
            "| Model | Old kept mean (range) | Old ids | New kept mean (range) | New ids | New PASS | New misses |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for model_id in SUITE_A:
        subset = [row for row in suite_a_main if row["model_id"] == model_id]
        old_entry = old.get(model_id, {})
        if subset:
            kept_values = [row["kept"] for row in subset]
            new_kept = f"{float(np.mean(kept_values)):.1f} ({min(kept_values)}-{max(kept_values)})"
            new_ids = sorted({identifier for row in subset for identifier in row["kept_ids"]})
            passes = f"{sum(row['expectation'] == 'PASS' for row in subset)}/{len(subset)}"
            misses = "; ".join(
                sorted({miss for row in subset for miss in row["misses"]})
            ) or "none"
        else:
            new_kept, new_ids, passes, misses = "n/a", [], "n/a", "n/a"
        lines.append(
            f"| {model_id} | "
            f"{old_entry.get('mean', float('nan')):.1f} ({old_entry.get('range', 'n/a')}) | "
            f"{', '.join(old_entry.get('ids', [])) or 'none'} | "
            f"{new_kept} | "
            f"{', '.join(new_ids) or 'none'} | {passes} | {misses} |"
        )

    lines.extend(
        [
            "",
            "## Fairlearn comparison (same data)",
            "",
            f"Fairlearn is fitted on **{fairlearn_n:,} synthetic applicants, seed "
            f"{fairlearn_seed}**, scored by every model over the same HTTP "
            "sandbox. DP = maximum approval-rate gap; EO = larger of the TPR/FPR "
            "gaps against the generator's hidden repayment label. These are "
            "observational gaps, not counterfactual findings, and lower is not "
            "automatically fair.",
            "",
            "| Model | Max DP gap (attribute) | DP gender | DP age | EO gender | EO age | FairLens kept (2%) |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for model_id in SUITE_B:
        subset = [row for row in fairlearn_rows if row["model_id"] == model_id]
        if not subset:
            continue
        by_attribute = {row["attribute"]: row for row in subset}
        gap_rows = [
            (float(row["dp_difference"]), row["attribute"])
            for row in subset
            if row["dp_difference"] != ""
        ]
        max_gap, max_attribute = max(gap_rows) if gap_rows else (0.0, "n/a")
        audit = [row for row in suite_b_main if row["model_id"] == model_id]
        kept = (
            f"{np.mean([row['kept'] for row in audit]):.1f}"
            if audit
            else "n/a"
        )
        lines.append(
            f"| {model_id} | {max_gap:.4f} ({max_attribute}) | "
            f"{by_attribute.get('gender', {}).get('dp_difference', '')} | "
            f"{by_attribute.get('age_band', {}).get('dp_difference', '')} | "
            f"{by_attribute.get('gender', {}).get('eo_difference', '')} | "
            f"{by_attribute.get('age_band', {}).get('eo_difference', '')} | {kept} |"
        )

    lines.extend(
        [
            "",
            "Models 14 and 15 are the useful contrast: the observational gaps are "
            "real, but the group twins never move the decision (Model 14 moves on "
            "loan amount, Model 15 has no group term at all), so the counterfactual "
            "audit keeps nothing. A Fairlearn-only review cannot tell those cases "
            "apart from a planted group penalty.",
            "",
            "## Cells, candidates, confirmation, and MDE",
            "",
            f"- Every suite B audit examined "
            f"{', '.join(str(count) for count in sorted({row['cells_examined'] for row in suite_b_main})) or '110'} "
            "discovery cells (5 main effects, 89 depth-1 contexts, 16 deep-panel "
            "cells in the pre-registered panel), with Holm applied to every cell in "
            "the family.",
            "- Discovery pairs, confirmation pairs, candidates, and confirmed cells "
            "are in `suite_b.csv`; confirmation uses 400 fresh pairs per candidate "
            "and at most 16 candidates.",
            "- MDE is the pre-registered planning approximation with power 0.80 and "
            "assumed discordance 0.25; it is not a post-hoc power claim.",
            "",
            "## Honest limitations",
            "",
            "- Synthetic applicants and synthetic names/pincodes only; this is not "
            "evidence about a real lender or real Indian populations.",
            *[
                bullet
                for bullet in (
                    merge_limitation,
                    sibling_limitation,
                    model_11_limitation,
                )
                if bullet
            ],
            "- Model 14's pre-registered criterion \"at least one rejected candidate "
            "cites loan amount\" is reported as a **miss**. Model 14 has no group "
            "term, so no cell reaches discovery and the Skeptic never sees a "
            "candidate; the legitimate-feature explanation is only visible in the "
            "observational gaps and the loan-amount context cells. This is a gap in "
            "the pre-registration, not a reason to add a post-hoc check.",
            "- Suite A's new-protocol pass checks are semantic re-implementations of "
            "the frozen expectations; the frozen `expectation_check` is unchanged "
            "and its old-protocol rows remain the recorded suite A result.",
            runtime_limitation,
            "",
            "## Artifacts",
            "",
            "- `suite_b.csv` - every audit row (suite, model, seed, materiality).",
            "- `suite_b_fairlearn.csv` - Fairlearn DP/EO for models 8-15.",
            "- `suite_b.md` - this file.",
            "",
        ]
    )
    if errors:
        lines.extend(["## Errors", ""])
        for row in errors:
            lines.append(
                f"- model {row['model_id']} seed {row['seed']} m={row['materiality']}: {row['error']}"
            )
    path = RESULTS / "suite_b.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="8,9,10,11,12,13,14,15")
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-sensitivity", action="store_true")
    parser.add_argument("--skip-suite-a", action="store_true")
    parser.add_argument("--skip-fairlearn", action="store_true")
    args = parser.parse_args(argv)

    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    models = [int(value) for value in args.models.split(",") if value.strip()]
    config = load_config()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RESULTS.mkdir(parents=True, exist_ok=True)

    processes, urls = start_servers(max(1, args.workers))
    tasks: list[dict[str, Any]] = []
    for index, model_id in enumerate(models):
        for seed in seeds:
            tasks.append(
                {
                    "suite": "B",
                    "model_id": model_id,
                    "seed": seed,
                    "materiality": float(config["audit"]["materiality"]),
                    "api_url": urls[index % len(urls)],
                }
            )
    if not args.skip_suite_a:
        for index, model_id in enumerate(SUITE_A):
            for seed in seeds:
                tasks.append(
                    {
                        "suite": "A",
                        "model_id": model_id,
                        "seed": seed,
                        "materiality": float(config["audit"]["materiality"]),
                        "api_url": urls[index % len(urls)],
                    }
                )
    if not args.skip_sensitivity:
        for index, model_id in enumerate(models):
            for materiality in MATERIALITIES:
                for seed in seeds:
                    tasks.append(
                        {
                            "suite": "B",
                            "model_id": model_id,
                            "seed": seed,
                            "materiality": materiality,
                            "api_url": urls[index % len(urls)],
                        }
                    )

    rows: list[dict[str, Any]] = []
    try:
        print(
            f"Starting {len(tasks)} generalized audits with {len(urls)} sandbox "
            f"servers and {args.workers} workers..."
        )
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(_audit_task, task) for task in tasks]
            for completed, future in enumerate(as_completed(futures), 1):
                row = future.result()
                rows.append(row)
                print(
                    f"[{completed:3d}/{len(tasks)}] suite={row['suite']} "
                    f"model={row['model_id']} seed={row['seed']} "
                    f"m={row['materiality']:.2f} kept={row['kept']} "
                    f"{row['expectation']:4s} {row['runtime_s']:6.1f}s"
                    + (f" ERROR={row['error']}" if row["error"] else "")
                )

        csv_path = _write_csv(rows)
        print(f"Wrote {csv_path.relative_to(REPO_ROOT)}")

        fairlearn_rows: list[dict[str, Any]] = []
        fairlearn_seed = int(config["seed"])
        fairlearn_n = int(config["data"]["n_observational"])
        if not args.skip_fairlearn:
            print("Building the Fairlearn comparison on one shared sample...")
            fairlearn_rows = _fairlearn(
                urls[0], fairlearn_n, fairlearn_seed, config
            )
            fairlearn_path = _write_fairlearn_csv(fairlearn_rows)
            print(f"Wrote {fairlearn_path.relative_to(REPO_ROOT)}")

        markdown = _write_markdown(
            rows, fairlearn_rows, fairlearn_seed, fairlearn_n, started_at
        )
        print(f"Wrote {markdown.relative_to(REPO_ROOT)}")
        return 0 if all(not row["error"] for row in rows) else 1
    finally:
        stop_servers(processes)


if __name__ == "__main__":
    raise SystemExit(main())
