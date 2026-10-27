"""Full evaluation: seven models x five seeds, plus threshold sensitivity.

Run from the repository root:

    .venv\\Scripts\\python -m eval.run_eval

The script starts several sandbox processes, runs the pre-registered audit in
parallel, and writes CSV, Markdown, and PNG artifacts under ``eval/results``.
It never edits ``config.yaml``; the 1%/3% sensitivity uses an in-memory copy.
"""

from __future__ import annotations

import argparse
import csv
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from auditor.pipeline import collect_audit
from auditor.run_table import expectation_check
from config_loader import REPO_ROOT, load_config, with_overrides
from eval.charts import PALETTE, grouped_bar, line_chart, simple_bar
from eval.sandbox_runner import start_servers, stop_servers
from impact.mitigate import build_curve, recommend
from trust.certificate import (
    build_certificate_payload,
    fresh_demo_db,
    issue,
    tamper_for_demo,
    verify,
)

RESULTS = REPO_ROOT / "eval" / "results"
CLEAN_MODELS = {1, 6, 7}
MATERIALITIES = (0.01, 0.03)


# ----------------------------------------------------------------------- audit
def _prefiltered(finding, alpha: float, materiality: float) -> bool:
    return (
        finding.evidence.n > 0
        and finding.evidence.p_adjusted < alpha
        and finding.evidence.net_flip_rate >= materiality
    )


def _audit_task(task: dict[str, Any]) -> dict[str, Any]:
    """Worker process: one audit. Returns a picklable summary."""

    config = load_config()
    materiality = float(task["materiality"])
    if materiality != float(config["audit"]["materiality"]):
        config = with_overrides(config, {"audit.materiality": materiality})
    started = time.perf_counter()
    try:
        _, report = collect_audit(
            int(task["model_id"]),
            str(task["api_url"]),
            config,
            seed=int(task["seed"]),
            include_mitigation=False,
            include_narrative=bool(task["include_narrative"]),
        )
        seconds = time.perf_counter() - started
        kept = [finding for finding in report.findings if finding.status == "kept"]
        rejected = [finding for finding in report.findings if finding.status == "rejected"]
        immaterial = [
            finding for finding in report.findings if finding.status == "immaterial"
        ]
        verdict, misses = expectation_check(report.model_id, report.findings)
        check = report.number_check_result or {}
        primary = max(kept, key=lambda f: f.evidence.net_flip_rate) if kept else None
        return {
            "kind": task["kind"],
            "model_id": int(task["model_id"]),
            "seed": int(task["seed"]),
            "materiality": materiality,
            "runtime_s": round(seconds, 2),
            "kept": len(kept),
            "rejected": len(rejected),
            "immaterial": len(immaterial),
            "kept_ids": [finding.id for finding in kept],
            "expectation": verdict,
            "misses": misses,
            "false_alarm_before": (
                sum(
                    1
                    for finding in report.findings
                    if _prefiltered(
                        finding,
                        float(config["audit"]["alpha"]),
                        float(config["audit"]["materiality"]),
                    )
                )
                if report.model_id in CLEAN_MODELS
                else None
            ),
            "false_alarm_after": (
                len(kept) if report.model_id in CLEAN_MODELS else None
            ),
            "narrative_source": check.get("source", ""),
            "number_check_passed": bool(check.get("passed", False)),
            "number_check_tokens": int(check.get("numeric_tokens", 0)),
            "primary": (
                {
                    "id": primary.id,
                    "kind": primary.kind,
                    "target_group": primary.target_group,
                    "attribute_or_subgroup": primary.attribute_or_subgroup,
                    "net_flip_rate": primary.evidence.net_flip_rate,
                    "p_adjusted": primary.evidence.p_adjusted,
                    "observational_gap": primary.observational_gap,
                }
                if primary
                else None
            ),
            "error": "",
            "report": report if task["kind"] == "main" else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": task["kind"],
            "model_id": int(task["model_id"]),
            "seed": int(task["seed"]),
            "materiality": materiality,
            "runtime_s": round(time.perf_counter() - started, 2),
            "kept": 0,
            "rejected": 0,
            "immaterial": 0,
            "kept_ids": [],
            "expectation": "ERROR",
            "misses": [f"{type(exc).__name__}: {exc}"],
            "false_alarm_before": None,
            "false_alarm_after": None,
            "narrative_source": "",
            "number_check_passed": False,
            "number_check_tokens": 0,
            "primary": None,
            "error": f"{type(exc).__name__}: {exc}",
            "report": None,
        }


def _segment(finding: dict[str, Any]) -> dict[str, str]:
    if finding["kind"] == "single_attribute":
        attribute = finding["attribute_or_subgroup"].split("=", 1)[0]
        return {attribute: finding["target_group"]}
    gender, age_band, urban_rural = finding["target_group"].split("|")
    return {
        "gender": gender,
        "age_band": age_band,
        "urban_rural": urban_rural,
    }


# --------------------------------------------------------------------- outputs
def _write_main_csv(rows: list[dict[str, Any]]) -> Path:
    path = RESULTS / "results.csv"
    fields = [
        "model_id",
        "seed",
        "materiality",
        "runtime_s",
        "runtime_under_60",
        "kept",
        "rejected",
        "immaterial",
        "kept_ids",
        "expectation",
        "misses",
        "false_alarm_before",
        "false_alarm_after",
        "narrative_source",
        "number_check_passed",
        "number_check_tokens",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["model_id"], item["seed"])):
            writer.writerow(
                {
                    "model_id": row["model_id"],
                    "seed": row["seed"],
                    "materiality": row["materiality"],
                    "runtime_s": row["runtime_s"],
                    "runtime_under_60": row["runtime_s"] < 60,
                    "kept": row["kept"],
                    "rejected": row["rejected"],
                    "immaterial": row["immaterial"],
                    "kept_ids": ";".join(row["kept_ids"]),
                    "expectation": row["expectation"],
                    "misses": "; ".join(row["misses"]),
                    "false_alarm_before": (
                        "" if row["false_alarm_before"] is None else row["false_alarm_before"]
                    ),
                    "false_alarm_after": (
                        "" if row["false_alarm_after"] is None else row["false_alarm_after"]
                    ),
                    "narrative_source": row["narrative_source"],
                    "number_check_passed": row["number_check_passed"],
                    "number_check_tokens": row["number_check_tokens"],
                    "error": row["error"],
                }
            )
    return path


def _write_sensitivity_csv(rows: list[dict[str, Any]]) -> Path:
    path = RESULTS / "materiality_sensitivity.csv"
    fields = [
        "model_id",
        "seed",
        "materiality",
        "kept",
        "kept_ids",
        "expectation",
        "misses",
        "false_alarm_before",
        "false_alarm_after",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(
            rows, key=lambda item: (item["model_id"], item["materiality"], item["seed"])
        ):
            writer.writerow(
                {
                    "model_id": row["model_id"],
                    "seed": row["seed"],
                    "materiality": row["materiality"],
                    "kept": row["kept"],
                    "kept_ids": ";".join(row["kept_ids"]),
                    "expectation": row["expectation"],
                    "misses": "; ".join(row["misses"]),
                    "false_alarm_before": (
                        "" if row["false_alarm_before"] is None else row["false_alarm_before"]
                    ),
                    "false_alarm_after": (
                        "" if row["false_alarm_after"] is None else row["false_alarm_after"]
                    ),
                }
            )
    return path


def _mitigation(
    models: list[int], api_url: str, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    curve_rows: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    default_budget = float(config["mitigation"]["max_accuracy_loss_default"])
    seed = int(config["seed"])
    for model_id in sorted(models):
        # The main evaluation uses seeds 1-5; the mitigation section is fixed at
        # the demo seed (42) and needs its own audit to find the primary finding.
        _, report = collect_audit(
            model_id,
            api_url,
            config,
            seed=seed,
            include_mitigation=False,
            include_narrative=False,
        )
        kept = [finding for finding in report.findings if finding.status == "kept"]
        if not kept:
            continue
        primary = max(kept, key=lambda finding: finding.evidence.net_flip_rate)
        segment = _segment(
            {
                "kind": primary.kind,
                "attribute_or_subgroup": primary.attribute_or_subgroup,
                "target_group": primary.target_group,
            }
        )
        print(
            f"Mitigation audit: model {model_id} seed {seed} "
            f"segment {primary.target_group} net {primary.evidence.net_flip_rate:.4f}"
        )
        curve = build_curve(
            model_id=model_id,
            api_url=api_url,
            segment=segment,
            config=config,
            seed=seed + 31_000,
        )
        for point in curve:
            curve_rows.append(
                {
                    "model_id": model_id,
                    "finding_id": primary.id,
                    "segment": primary.target_group,
                    **point,
                }
            )
        rec = recommend(curve, default_budget)
        if rec is None:
            continue
        recommendations.append(
            {
                "model_id": model_id,
                "finding_id": primary.id,
                "segment": primary.target_group,
                "offset": rec["offset"],
                "fairness_gap": rec["fairness_gap"],
                "accuracy_loss": rec["accuracy_loss"],
                "accuracy": rec["accuracy"],
                "sampling": rec["sampling"],
                "default_budget": default_budget,
            }
        )
    path = RESULTS / "mitigation_curves.csv"
    fields = [
        "model_id",
        "finding_id",
        "segment",
        "offset",
        "segment_approval_rate",
        "comparison_approval_rate",
        "fairness_gap",
        "signed_gap",
        "accuracy",
        "accuracy_loss",
        "segment_n",
        "comparison_n",
        "base_accuracy",
        "sampling",
        "segment_share",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(curve_rows)
    return curve_rows, recommendations


def _certificate_test(report, config: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="fairlens-eval-cert-") as temp:
        db_path = fresh_demo_db(Path(temp) / "eval-certificates.db")
        payload = build_certificate_payload(report, config, "Evaluation Auditor", "approve")
        empty_name_rejected = False
        try:
            issue(payload, "", "approve", db_path)
        except ValueError:
            empty_name_rejected = True
        certificate = issue(payload, "Evaluation Auditor", "approve", db_path)
        verified_before, _ = verify(db_path)
        tamper_for_demo(certificate.index, db_path)
        verified_after, broken = verify(db_path)
        return {
            "empty_name_rejected": empty_name_rejected,
            "verified_before": verified_before,
            "verified_after": verified_after,
            "broken_index": broken,
            "certificate_hash": certificate.record_hash,
        }


def _plot_main(main_rows: list[dict[str, Any]]) -> None:
    models = sorted({row["model_id"] for row in main_rows})
    means = []
    lows = []
    highs = []
    for model in models:
        values = [row["kept"] for row in main_rows if row["model_id"] == model]
        means.append(float(np.mean(values)))
        lows.append(float(np.min(values)))
        highs.append(float(np.max(values)))
    simple_bar(
        RESULTS / "kept_findings_by_model.png",
        [f"Model {model}" for model in models],
        means,
        ["#2f855a" if model in CLEAN_MODELS else "#b42318" for model in models],
        title="Kept findings by model (range bars; green = expected-clean controls)",
        ylabel="Mean kept findings across 5 seeds",
        ranges=list(zip(lows, highs)),
    )

    series = []
    for index, model in enumerate(models):
        subset = sorted(
            [row for row in main_rows if row["model_id"] == model],
            key=lambda item: item["seed"],
        )
        values = [
            (row["primary"]["net_flip_rate"] * 100) if row["primary"] else 0.0
            for row in subset
        ]
        series.append((f"Model {model}", values, PALETTE[index % len(PALETTE)]))
    line_chart(
        RESULTS / "primary_net_flip_by_seed.png",
        [str(seed) for seed in sorted({row["seed"] for row in main_rows})],
        series,
        title="Largest kept counterfactual effect by seed",
        ylabel="Primary kept net flip (%)",
        reference_value=2.0,
        reference_label="Materiality 2%",
    )


def _plot_sensitivity(
    main_rows: list[dict[str, Any]], sensitivity_rows: list[dict[str, Any]]
) -> None:
    models = sorted({row["model_id"] for row in main_rows})
    colors = {0.01: "#b42318", 0.02: "#475467", 0.03: "#175cd3"}
    series = []
    for materiality in (0.01, 0.02, 0.03):
        source = (
            main_rows
            if materiality == 0.02
            else [
                row
                for row in sensitivity_rows
                if abs(row["materiality"] - materiality) < 1e-9
            ]
        )
        values = [
            float(np.mean([row["kept"] for row in source if row["model_id"] == model]))
            for model in models
        ]
        series.append((f"Materiality {materiality:.0%}", values, colors[materiality]))
    grouped_bar(
        RESULTS / "materiality_sensitivity.png",
        [f"Model {model}" for model in models],
        series,
        title="Materiality sensitivity (pre-registered run stays at 2%)",
        ylabel="Mean kept findings across 5 seeds",
    )


def _plot_mitigation(curve_rows: list[dict[str, Any]]) -> None:
    if not curve_rows:
        return
    series = []
    offsets = sorted({row["offset"] for row in curve_rows})
    for index, model in enumerate(sorted({row["model_id"] for row in curve_rows})):
        subset = sorted(
            [row for row in curve_rows if row["model_id"] == model],
            key=lambda item: item["offset"],
        )
        series.append(
            (
                f"Model {model}",
                [row["fairness_gap"] * 100 for row in subset],
                PALETTE[index % len(PALETTE)],
            )
        )
    line_chart(
        RESULTS / "mitigation_curves.png",
        [str(offset) for offset in offsets],
        series,
        title="Mitigation trade-off at seed 42 (absolute segment gap)",
        ylabel="Absolute fairness gap (%)",
    )


def _aggregate(main_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregates = []
    for model in sorted({row["model_id"] for row in main_rows}):
        subset = [row for row in main_rows if row["model_id"] == model]
        kept_values = [row["kept"] for row in subset]
        missing = [miss for row in subset for miss in row["misses"]]
        aggregates.append(
            {
                "model_id": model,
                "runs": len(subset),
                "expectation_pass": sum(row["expectation"] == "PASS" for row in subset),
                "kept_mean": float(np.mean(kept_values)),
                "kept_range": f"{min(kept_values)}-{max(kept_values)}",
                "false_before": sum(
                    row["false_alarm_before"] or 0 for row in subset
                )
                if model in CLEAN_MODELS
                else None,
                "false_after": sum(row["false_alarm_after"] or 0 for row in subset)
                if model in CLEAN_MODELS
                else None,
                "number_check_pass": sum(row["number_check_passed"] for row in subset),
                "runtime_mean": float(np.mean([row["runtime_s"] for row in subset])),
                "misses": sorted(set(missing)),
            }
        )
    return aggregates


def _write_summary(
    main_rows: list[dict[str, Any]],
    sensitivity_rows: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    certificate: dict[str, Any],
    started_at: str,
) -> Path:
    aggregates = _aggregate(main_rows)
    total_runs = len(main_rows)
    total_audit_seconds = sum(row["runtime_s"] for row in main_rows)
    number_checks = sum(row["number_check_passed"] for row in main_rows)
    errors = [row for row in main_rows if row["error"]]
    misses = sorted({miss for row in main_rows for miss in row["misses"]})

    lines = [
        "# FairLens India evaluation summary",
        "",
        f"Generated: {started_at}",
        "",
        "Pre-registered run: **7 models x 5 seeds (35 audits)**, seed 42-style "
        "config unchanged, alpha 0.05, materiality 2%, Holm correction, 2,000 "
        "single-attribute twin pairs, 500 pairs per intersectional cell. No "
        "threshold, penalty, or population parameter was tuned after the first "
        "audit.",
        "",
        "The audit used a real HTTP sandbox. Each model/seed pair is an "
        "independent audit. Runtimes below are wall-clock times measured inside "
        "the parallel evaluation workers, so they are indicative, not a "
        "single-user demo benchmark. The serial demo benchmark is in "
        "`phase5_demo_smoke.md`.",
        "",
        "## Main results",
        "",
        "| Model | Runs | Expectation PASS | Kept mean (range) | False alarms before -> after | "
        "Number check | Mean runtime | Misses |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in aggregates:
        false_text = (
            f"{row['false_before']} -> {row['false_after']}"
            if row["false_before"] is not None
            else "n/a"
        )
        lines.append(
            f"| {row['model_id']} | {row['runs']} | {row['expectation_pass']}/{row['runs']} | "
            f"{row['kept_mean']:.1f} ({row['kept_range']}) | {false_text} | "
            f"{row['number_check_pass']}/{row['runs']} | {row['runtime_mean']:.1f}s | "
            f"{'none' if not row['misses'] else '; '.join(row['misses'])} |"
        )
    lines.extend(
        [
            "",
            f"- Completed audits: **{total_runs}**; errors: **{len(errors)}**.",
            f"- Narrative number-check pass rate: **{number_checks}/{total_runs} "
            f"({100 * number_checks / max(total_runs, 1):.1f}%)**.",
            f"- Total audit compute time: **{total_audit_seconds:.1f}s** "
            f"(mean {total_audit_seconds / max(total_runs, 1):.1f}s).",
            "",
            "## False alarms and misses",
            "",
            "A false alarm before the Skeptic is a candidate that is Holm-"
            "significant and has net flip >= materiality in a model with no "
            "planted penalty (Models 1, 6, 7). After the Skeptic means kept.",
            "",
        ]
    )
    clean_rows = [
        row
        for row in aggregates
        if row["model_id"] in CLEAN_MODELS
    ]
    for row in clean_rows:
        lines.append(
            f"- Model {row['model_id']}: before **{row['false_before']}**, "
            f"after **{row['false_after']}** across {row['runs']} seeds."
        )
    lines.extend(
        [
            "",
            "### Expectations that did not pass",
            "",
        ]
    )
    if misses:
        for miss in misses:
            lines.append(f"- {miss}")
        lines.append(
            "- Model 5's single-attribute gender finding is the known D-009 "
            "pre-registration miss. The hotspot is 4% of male-origin pairs, not "
            "2% of the whole population, so the diluted net rate is about 0.025 "
            "rather than 0.012. The materiality threshold was not changed."
        )
    else:
        lines.append("- None. Every pre-registered expectation passed.")
    lines.extend(
        [
            "",
            "## Mitigation (seed 42, default 2% accuracy-loss budget)",
            "",
            "| Model | Segment | Offset | Fairness gap | Accuracy loss | Sampling |",
            "|---|---|---|---|---|---|",
        ]
    )
    for rec in recommendations:
        segment = str(rec["segment"]).replace("|", " · ")
        lines.append(
            f"| {rec['model_id']} | {segment} | +{rec['offset']} | "
            f"{float(rec['fairness_gap']) * 100:.2f}% | "
            f"{float(rec['accuracy_loss']) * 100:+.2f}% | {rec['sampling']} |"
        )
    if not recommendations:
        lines.append("| none | none | - | - | - | - |")
    lines.extend(
        [
            "",
            "Negative accuracy loss means the offset improved agreement with the "
            "hidden repayment label on the mitigation sample. It is not a causal "
            "claim about real lending.",
            "",
            "## Certificate test",
            "",
            f"- Empty approver rejected: **{certificate['empty_name_rejected']}**",
            f"- Chain valid before tamper: **{certificate['verified_before']}**",
            f"- Chain valid after tamper: **{certificate['verified_after']}** "
            f"(first broken record: {certificate['broken_index']})",
            f"- Certificate hash: `{certificate['certificate_hash']}`",
            "",
            "The hash chain proves tamper-evidence, not authorship. A signer with "
            "write access could recompute the whole chain; digital signatures are "
            "future work.",
            "",
            "## Materiality sensitivity",
            "",
            "The pre-registered 2% run is reported above. The two sensitivity runs "
            "copy the config in memory to 1% and 3%; no file is edited. They use "
            "the same seeds and statistics.",
            "",
        ]
    )
    if not sensitivity_rows:
        lines.append("- Sensitivity runs were skipped in this invocation.")
    else:
        lines.extend(
            [
                "| Model | Kept mean at 1% | Kept mean at 2% | Kept mean at 3% |",
                "|---|---|---|---|",
            ]
        )
        for model in sorted({row["model_id"] for row in main_rows}):
            values = []
            for materiality in (0.01, 0.02, 0.03):
                source = (
                    main_rows
                    if materiality == 0.02
                    else [
                        row
                        for row in sensitivity_rows
                        if abs(row["materiality"] - materiality) < 1e-9
                    ]
                )
                values.append(
                    float(
                        np.mean(
                            [row["kept"] for row in source if row["model_id"] == model]
                        )
                    )
                )
            lines.append(
                f"| {model} | {values[0]:.1f} | {values[1]:.1f} | {values[2]:.1f} |"
            )
        lines.extend(
            [
                "",
                "Model 5 is the borderline case. Its single-attribute gender finding "
                "is kept in the 2% pre-registered run and moves with the threshold, "
                "while the intersectional hotspot stays dominant. The raw per-seed "
                "rows are in `materiality_sensitivity.csv`.",
            ]
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `results.csv` - every main audit (35 rows).",
            "- `materiality_sensitivity.csv` - 1% and 3% audits (70 rows).",
            "- `mitigation_curves.csv` - full offset sweeps at seed 42.",
            "- `kept_findings_by_model.png`, `primary_net_flip_by_seed.png`, "
            "`materiality_sensitivity.png`, `mitigation_curves.png`.",
            "- `fairlearn.md` / `fairlearn.csv` - observational baseline.",
            "- `phase5_demo_smoke.md` - serial three-model demo and certificate "
            "tamper check.",
            "",
            "## Honest limitations",
            "",
            "- Synthetic applicants and synthetic names/pincodes only; not evidence "
            "about a real lender or real Indian populations.",
            "- Twin probing is evidence of disparate treatment, not proof of intent. "
            "The Skeptic is rule-based, not omniscient.",
            "- Observational DP/EO gaps can be caused by legitimate income "
            "differences; Model 7 demonstrates why a baseline alone is not enough.",
            "- The certificate is tamper-evident, not signed. It does not establish "
            "authorship.",
            "- Model 5's single-gender kept finding remains a pre-registration miss; "
            "it is reported, not hidden or retuned.",
            "",
        ]
    )
    path = RESULTS / "summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="1,2,3,4,5,6,7")
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--skip-sensitivity", action="store_true")
    parser.add_argument("--skip-mitigation", action="store_true")
    args = parser.parse_args(argv)

    models = [int(value) for value in args.models.split(",") if value.strip()]
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    config = load_config()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RESULTS.mkdir(parents=True, exist_ok=True)

    processes, urls = start_servers(max(1, args.workers))
    tasks: list[dict[str, Any]] = []
    for index, model in enumerate(models):
        for seed in seeds:
            tasks.append(
                {
                    "kind": "main",
                    "model_id": model,
                    "seed": seed,
                    "materiality": float(config["audit"]["materiality"]),
                    "include_narrative": True,
                    "api_url": urls[index % len(urls)],
                }
            )
    if not args.skip_sensitivity:
        for index, model in enumerate(models):
            for materiality in MATERIALITIES:
                for seed in seeds:
                    tasks.append(
                        {
                            "kind": "sensitivity",
                            "model_id": model,
                            "seed": seed,
                            "materiality": materiality,
                            "include_narrative": False,
                            "api_url": urls[index % len(urls)],
                        }
                    )

    results: list[dict[str, Any]] = []
    try:
        print(
            f"Starting {len(tasks)} audits with {len(urls)} sandbox servers "
            f"and {args.workers} workers..."
        )
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(_audit_task, task) for task in tasks]
            for completed, future in enumerate(as_completed(futures), 1):
                result = future.result()
                results.append(result)
                print(
                    f"[{completed:3d}/{len(tasks)}] {result['kind']:11s} "
                    f"model={result['model_id']} seed={result['seed']} "
                    f"m={result['materiality']:.2f} kept={result['kept']} "
                    f"{result['expectation']:4s} {result['runtime_s']:5.1f}s"
                    + (f" ERROR={result['error']}" if result["error"] else "")
                )

        main_rows = [row for row in results if row["kind"] == "main"]
        sensitivity_rows = [
            row for row in results if row["kind"] == "sensitivity"
        ]
        if not main_rows:
            raise RuntimeError("no main audit results")
        _write_main_csv(main_rows)
        if sensitivity_rows:
            _write_sensitivity_csv(sensitivity_rows)

        recommendations: list[dict[str, Any]] = []
        curve_rows: list[dict[str, Any]] = []
        if not args.skip_mitigation:
            print("Building mitigation curves at seed 42...")
            curve_rows, recommendations = _mitigation(models, urls[0], config)
            _plot_mitigation(curve_rows)

        seed42 = next(
            (
                row
                for row in main_rows
                if row["seed"] == int(config["seed"]) and row["model_id"] == 2
            ),
            None,
        )
        certificate_report = (
            seed42["report"] if seed42 else next(row["report"] for row in main_rows)
        )
        certificate = _certificate_test(certificate_report, config)
        _plot_main(main_rows)
        if sensitivity_rows:
            _plot_sensitivity(main_rows, sensitivity_rows)
        summary = _write_summary(
            main_rows,
            sensitivity_rows,
            recommendations,
            certificate,
            started_at,
        )
        print(f"Wrote {summary.relative_to(REPO_ROOT)}")
        print(
            f"Certificate: before={certificate['verified_before']} "
            f"after={certificate['verified_after']} "
            f"broken={certificate['broken_index']}"
        )
        all_ok = all(not row["error"] for row in results)
        return 0 if all_ok else 1
    finally:
        stop_servers(processes)


if __name__ == "__main__":
    raise SystemExit(main())
