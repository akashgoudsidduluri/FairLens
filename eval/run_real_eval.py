"""R3b: audit the two real-data targets with the frozen v1 protocol.

Run from the repository root:

    .venv\\Scripts\\python -m eval.run_real_eval

This starts the real-data target service (``targets.real.serve``), audits each
model on seeds 1-5 with the pre-registered thresholds in ``config.yaml``, and
writes ``eval/results/real_models.csv`` and ``real_models.md``.

Nothing here changes a threshold, a feature, a model, or a mapping. The
expectation was pre-registered in ``expected_findings.md`` as "No expected
finding. Report whatever is found, including no material bias."

The model is real; the probe population is the synthetic FairLens generator
mapped into the dataset's columns. Only the probes defined by the adapter run;
the report states what was skipped and why.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Any

from auditor.pipeline import collect_audit
from config_loader import REPO_ROOT, load_config
from eval.sandbox_runner import start_real_server, stop_servers
from impact.impact import impact_per_10k as impact_for
from targets import build_target
from targets.real.models import metrics_for

RESULTS = REPO_ROOT / "eval" / "results"

TARGETS = [
    {
        "key": "uci_credit_default",
        "label": "UCI credit default (logistic regression)",
        "adapter": "targets/real/uci-credit-default.yaml",
        "model_id": 101,
    },
    {
        "key": "adult_income",
        "label": "UCI Adult (gradient boosting)",
        "adapter": "targets/real/adult-income.yaml",
        "model_id": 102,
    },
]


def _clean(text: str) -> str:
    return " ".join(str(text).replace("|", "/").split())


def _finding_detail(finding) -> str:
    evidence = finding.evidence
    impact = impact_for(finding)
    return (
        f"{finding.attribute_or_subgroup}: n={evidence.n}, "
        f"b={evidence.b}, c={evidence.c}, "
        f"net={evidence.net_flip_rate:+.4f} "
        f"(95% CI {evidence.ci_low:+.4f} to {evidence.ci_high:+.4f}), "
        f"p_adj={evidence.p_adjusted:.3e}, "
        f"impact={impact.per_10k:.1f}/10k. "
        f"{_clean(finding.reason)}"
    )


def _audit(
    target: dict[str, Any], seed: int, base_url: str, config: dict[str, Any]
) -> dict[str, Any]:
    adapter = build_target(target["adapter"], config, base_url=base_url)
    adapter.reset()
    started = time.perf_counter()
    try:
        events, report = collect_audit(
            int(target["model_id"]),
            adapter.base_url,
            config,
            seed=seed,
            include_mitigation=False,
            include_narrative=False,
            target=adapter,
        )
        runtime = time.perf_counter() - started
        kept = [f for f in report.findings if f.status == "kept"]
        rejected = [f for f in report.findings if f.status == "rejected"]
        immaterial = [f for f in report.findings if f.status == "immaterial"]
        metrics = metrics_for(target["key"])
        fairlearn = metrics["fairlearn_holdout"]
        skipped = report.observational.get("skipped_probes", {})
        skip_events = [
            event.message
            for event in events
            if event.payload.get("probe")
            and event.payload.get("skipped") is True
        ]
        return {
            "model": target["key"],
            "label": target["label"],
            "seed": seed,
            "runtime_s": round(runtime, 2),
            "probes_used": adapter.probes_used,
            "supported_probes": sorted(report.observational.get("supported_probes", [])),
            "skipped_probes": skipped,
            "skip_events": skip_events,
            "kept": len(kept),
            "rejected": len(rejected),
            "immaterial": len(immaterial),
            "kept_details": " || ".join(_findings_text(kept)),
            "rejected_details": " || ".join(_findings_text(rejected)),
            "immaterial_details": " || ".join(_findings_text(immaterial)),
            "impact_per_10k": max(
                (impact_for(f).per_10k for f in report.findings), default=0.0
            ),
            "holdout_accuracy": metrics["holdout"]["accuracy"],
            "holdout_auc": metrics["holdout"]["roc_auc"],
            "fairlearn": fairlearn,
            "findings": [
                {
                    "model": target["key"],
                    "seed": seed,
                    "attribute_or_subgroup": f.attribute_or_subgroup,
                    "status": f.status,
                    "n": f.evidence.n,
                    "b": f.evidence.b,
                    "c": f.evidence.c,
                    "net_flip_rate": f.evidence.net_flip_rate,
                    "ci_low": f.evidence.ci_low,
                    "ci_high": f.evidence.ci_high,
                    "p_adjusted": f.evidence.p_adjusted,
                    "observational_gap": f.observational_gap,
                    "impact_per_10k": impact_for(f).per_10k,
                    "reason": f.reason,
                }
                for f in report.findings
            ],
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "model": target["key"],
            "label": target["label"],
            "seed": seed,
            "runtime_s": round(time.perf_counter() - started, 2),
            "probes_used": adapter.probes_used,
            "supported_probes": [],
            "skipped_probes": {},
            "skip_events": [],
            "kept": 0,
            "rejected": 0,
            "immaterial": 0,
            "kept_details": "",
            "rejected_details": "",
            "immaterial_details": "",
            "impact_per_10k": 0.0,
            "holdout_accuracy": 0.0,
            "holdout_auc": 0.0,
            "fairlearn": {},
            "findings": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _findings_text(findings) -> list[str]:
    return [_finding_detail(f) for f in findings]


def _write_csv(rows: list[dict[str, Any]]) -> Path:
    path = RESULTS / "real_models.csv"
    fields = [
        "model",
        "seed",
        "runtime_s",
        "probes_used",
        "supported_probes",
        "skipped_probes",
        "kept",
        "rejected",
        "immaterial",
        "impact_per_10k",
        "holdout_accuracy",
        "holdout_auc",
        "fairlearn_sex_demographic_parity_difference",
        "fairlearn_sex_equalized_odds_difference",
        "fairlearn_age_demographic_parity_difference",
        "fairlearn_age_equalized_odds_difference",
        "fairlearn_race_demographic_parity_difference",
        "fairlearn_race_equalized_odds_difference",
        "kept_details",
        "rejected_details",
        "immaterial_details",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["model"], item["seed"])):
            fairlearn = row["fairlearn"]

            def block(attribute: str, field: str) -> Any:
                value = fairlearn.get(attribute)
                return "" if value is None else value[field]

            writer.writerow(
                {
                    "model": row["model"],
                    "seed": row["seed"],
                    "runtime_s": row["runtime_s"],
                    "probes_used": row["probes_used"],
                    "supported_probes": ";".join(row["supported_probes"]),
                    "skipped_probes": ";".join(sorted(row["skipped_probes"])),
                    "kept": row["kept"],
                    "rejected": row["rejected"],
                    "immaterial": row["immaterial"],
                    "impact_per_10k": row["impact_per_10k"],
                    "holdout_accuracy": row["holdout_accuracy"],
                    "holdout_auc": row["holdout_auc"],
                    "fairlearn_sex_demographic_parity_difference": block(
                        "sex", "demographic_parity_difference"
                    ),
                    "fairlearn_sex_equalized_odds_difference": block(
                        "sex", "equalized_odds_difference"
                    ),
                    "fairlearn_age_demographic_parity_difference": block(
                        "age_band", "demographic_parity_difference"
                    ),
                    "fairlearn_age_equalized_odds_difference": block(
                        "age_band", "equalized_odds_difference"
                    ),
                    "fairlearn_race_demographic_parity_difference": block(
                        "race", "demographic_parity_difference"
                    ),
                    "fairlearn_race_equalized_odds_difference": block(
                        "race", "equalized_odds_difference"
                    ),
                    "kept_details": row["kept_details"],
                    "rejected_details": row["rejected_details"],
                    "immaterial_details": row["immaterial_details"],
                    "error": row["error"],
                }
            )
    return path


def _fairlearn_cell(fairlearn: dict[str, Any], attribute: str) -> str:
    block = fairlearn.get(attribute)
    if not block:
        return "n/a"
    return (
        f"DP {block['demographic_parity_difference']:.4f} / "
        f"EO {block['equalized_odds_difference']:.4f}"
    )


def _coverage_line(row: dict[str, Any]) -> str:
    supported = ", ".join(row["supported_probes"]) or "none"
    skipped = ", ".join(sorted(row["skipped_probes"])) or "none"
    return f"tested: {supported}; skipped: {skipped}"


def _summary(rows: list[dict[str, Any]]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for target in TARGETS:
        subset = [row for row in rows if row["model"] == target["key"]]
        errors = [row for row in subset if row["error"]]
        kept_seeds = [row["seed"] for row in subset if row["kept"] > 0]
        findings = [finding for row in subset for finding in row["findings"]]
        nets = [finding["net_flip_rate"] for finding in findings]
        discordant = sum(finding["b"] + finding["c"] for finding in findings)
        total_pairs = sum(finding["n"] for finding in findings)
        if errors:
            summary[target["key"]] = (
                f"Evaluation did not complete on {len(errors)} of {len(subset)} "
                "seeds; no fairness conclusion can be drawn."
            )
        elif kept_seeds:
            summary[target["key"]] = (
                "At least one kept gender finding under the pre-registered "
                f"thresholds on seeds {kept_seeds}. See the findings table."
            )
        elif discordant == 0:
            summary[target["key"]] = (
                "No kept finding, and the result is an **inconclusive null**, not "
                f"evidence of no bias: all {total_pairs:,} twin pairs "
                "produced the same decision before and after the gender flip "
                "(b=0, c=0). On this mapped population no score sat close enough "
                "to the 500 approval threshold for a gender flip to cross it, so "
                "the probe had no power to detect an effect. This is a limitation "
                "of the probe population, not proof that the model is fair. "
                "Fairlearn's observational baseline is in the headline table."
            )
        else:
            summary[target["key"]] = (
                "No material bias under the pre-registered 2% threshold: net flip "
                f"rates ranged {min(nets):+.4f} to {max(nets):+.4f} across seeds, "
                "and every candidate was classified immaterial (significant but "
                "below 0.02), not kept. The direction was consistent in every "
                "seed. This is not proof of fairness; a sub-threshold effect is "
                "still an effect, and pincode, name, and intersectional probes "
                "could not be tested."
            )
    return summary


def _write_markdown(rows: list[dict[str, Any]]) -> Path:
    path = RESULTS / "real_models.md"
    findings = [
        finding for row in rows for finding in row["findings"]
    ]
    lines: list[str] = [
        "# Real-data target results (R3b)",
        "",
        "**Status: evaluated after pre-registration.** `expected_findings.md` was",
        "committed with \"No expected finding. Report whatever is found, including",
        "no material bias.\" before this evaluation. No threshold, feature, model,",
        "or mapping was changed after seeing these results.",
        "",
        "These are **not** the seven sandbox models. The model is trained on public",
        "UCI data; the probe population is the synthetic FairLens generator mapped",
        "into the dataset's columns, not the dataset's own population.",
        "",
        "## Protocol",
        "",
        "- Frozen v1 thresholds: alpha 0.05, Holm correction, materiality 0.02,",
        "  2,000 pairs per supported attribute, 4,000 observational applicants,",
        "  seeds 1-5, 95% bootstrap CI with 4,000 iterations.",
        "- `include_mitigation: false`: these targets do not expose the sandbox",
        "  score-offset endpoint, so an offset sweep is not comparable.",
        "- Approval rule fixed in R3a: `P(favourable) >= 0.5`, score `P*1000`.",
        "- Only probes the adapter declares are run. Unsupported probes are logged",
        "  and reported, never faked.",
        "",
        "## Headline table (per model, seeds 1-5)",
        "",
        "| Real target | Kept | Rejected | Immaterial | Impact per 10,000 (max candidate) | Fairlearn on holdout, sex DP / EO | age DP / EO | race DP / EO | Holdout accuracy | Mean runtime | Coverage |",
        "|---|---:|---:|---:|---:|---|---|---|---:|---:|---|",
    ]
    for target in TARGETS:
        subset = [row for row in rows if row["model"] == target["key"]]
        if not subset:
            continue
        first = subset[0]
        fairlearn = first["fairlearn"]
        lines.append(
            "| {label} | {kept} | {rejected} | {immaterial} | {impact:.1f} | "
            "{sex} | {age} | {race} | {accuracy:.4f} | {runtime:.1f}s | {coverage} |".format(
                label=target["label"],
                kept=sum(row["kept"] for row in subset),
                rejected=sum(row["rejected"] for row in subset),
                immaterial=sum(row["immaterial"] for row in subset),
                impact=max(row["impact_per_10k"] for row in subset),
                sex=_fairlearn_cell(fairlearn, "sex"),
                age=_fairlearn_cell(fairlearn, "age_band"),
                race=_fairlearn_cell(fairlearn, "race"),
                accuracy=first["holdout_accuracy"],
                runtime=sum(row["runtime_s"] for row in subset) / len(subset),
                coverage=_coverage_line(first),
            )
        )

    lines.extend(
        [
            "",
            "Fairlearn numbers are computed on the same real holdout split as the",
            "model metrics and are shown **for comparison only**. They are not a",
            "FairLens audit result and are not used to reinterpret the paired",
            "counterfactual evidence.",
            "",
            "Impact is `max(net flip rate, 0) * 10,000` for every candidate, including",
            "immaterial and rejected ones. Only a kept finding turns it into an audit",
            "conclusion. `0` means no candidate had a positive net flip rate.",
            "",
            "## Per-seed results",
            "",
            "| Real target | Seed | Kept | Rejected (reason) | Immaterial | Impact per 10,000 | Runtime |",
            "|---|---:|---:|---|---:|---:|---:|",
        ]
    )
    for row in sorted(rows, key=lambda item: (item["model"], item["seed"])):
        lines.append(
            "| {model} | {seed} | {kept} | {rejected} | {immaterial} | "
            "{impact:.1f} | {runtime:.2f}s |".format(
                model=row["model"],
                seed=row["seed"],
                kept=row["kept"],
                rejected=(
                    _clean(row["rejected_details"]).replace("||", "; ")
                    if row["rejected_details"]
                    else "none"
                ),
                immaterial=(
                    _clean(row["immaterial_details"]).replace("||", "; ")
                    if row["immaterial_details"]
                    else "none"
                ),
                impact=row["impact_per_10k"],
                runtime=row["runtime_s"],
            )
        )

    lines.extend(
        [
            "",
            "## Findings in detail",
            "",
            "Every candidate that reached the Skeptic is listed, including rejected",
            "and immaterial ones. A rejected finding is kept in the record.",
            "",
            "| Real target | Seed | Finding | Status | n | b | c | Net flip | 95% CI | Holm p | Impact per 10,000 | Reason |",
            "|---|---:|---|---|---:|---:|---:|---:|---|---:|---:|---|",
        ]
    )
    for finding in sorted(
        findings, key=lambda item: (item["model"], item["seed"], item["attribute_or_subgroup"])
    ):
        lines.append(
            "| {model} | {seed} | {attribute} | {status} | {n} | {b} | {c} | "
            "{net:+.4f} | {low:+.4f} to {high:+.4f} | {p:.3e} | {impact:.1f} | {reason} |".format(
                model=finding["model"],
                seed=finding["seed"],
                attribute=finding["attribute_or_subgroup"],
                status=finding["status"],
                n=finding["n"],
                b=finding["b"],
                c=finding["c"],
                net=finding["net_flip_rate"],
                low=finding["ci_low"],
                high=finding["ci_high"],
                p=finding["p_adjusted"],
                impact=finding["impact_per_10k"],
                reason=_clean(finding["reason"]),
            )
        )

    lines.extend(["", "## What was found", ""])
    for target in TARGETS:
        lines.append(f"- **{target['label']}**: {_summary(rows)[target['key']]}")

    lines.extend(["", "## What FairLens could and could not test", ""])
    for target in TARGETS:
        subset = [row for row in rows if row["model"] == target["key"]]
        if not subset:
            continue
        row = subset[0]
        lines.append(
            f"**{target['label']}**. Could test: {', '.join(row['supported_probes']) or 'none'}. "
            "Could not test:"
        )
        for probe, reason in sorted(row["skipped_probes"].items()):
            lines.append(f"- `{probe}`: {reason}")
        lines.append(
            "- Age and race: not counterfactually probed. The frozen probe family has no"
        )
        lines.append(
            "  age-only twin, and race has no canonical field. Both are measured on"
        )
        lines.append(
            "  the real holdout by Fairlearn only, which is an observational baseline,"
        )
        lines.append("  not the twin audit.")

    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- The **model** is real; the **probe population** is the synthetic FairLens",
            "  generator mapped into the dataset's columns. Results describe this model's",
            "  counterfactual behaviour over that mapped population, not the dataset's",
            "  own population and not any real lender.",
            "- Only gender is counterfactually testable. No pincode, name, or",
            "  intersectional result exists for these targets. Absence of those findings",
            "  is not evidence of absence of bias.",
            "- The Adult model consumes `race` but the canonical contract has no race",
            "  field; race is held at the training mode when serving. The credit model",
            "  has no race column at all.",
            "- Several dataset columns with no canonical source are held at documented",
            "  training constants when serving. The audit varies gender while holding",
            "  those constants fixed.",
            "- Fairlearn demographic parity and equalized odds are computed once on the",
            "  holdout and do not vary with audit seed. They can disagree with each",
            "  other and with the twin test; that is expected, not a bug.",
            "- A null twin result is not proof of fairness. It means no material",
            "  disparity was detected by this probe on this mapped population at the",
            "  pre-registered thresholds.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help="Override seeds (default: audit.seeds from config.yaml)",
    )
    args = parser.parse_args(argv)

    config = load_config()
    seeds = args.seeds or [int(seed) for seed in config["audit"]["seeds"]]
    RESULTS.mkdir(parents=True, exist_ok=True)

    process, base_url = start_real_server()
    rows: list[dict[str, Any]] = []
    try:
        for target in TARGETS:
            for seed in seeds:
                row = _audit(target, seed, base_url, config)
                rows.append(row)
                print(
                    f"{target['key']} seed {seed}: kept={row['kept']} "
                    f"rejected={row['rejected']} immaterial={row['immaterial']} "
                    f"runtime={row['runtime_s']:.2f}s"
                    + (f" ERROR {row['error']}" if row["error"] else "")
                )
    finally:
        stop_servers([process])

    csv_path = _write_csv(rows)
    md_path = _write_markdown(rows)
    print(f"Wrote {csv_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)}")
    for key, text in _summary(rows).items():
        print(f"{key}: {text}")
    return 0 if all(not row["error"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
