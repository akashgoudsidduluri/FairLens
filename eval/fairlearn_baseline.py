"""Observational fairness baseline using fairlearn.

Run from the repository root:

    .venv\\Scripts\\python -m eval.fairlearn_baseline

This is not the FairLens auditor. It uses one observational sample, the hidden
repayment labels, and fairlearn's demographic-parity and equalized-odds
differences. FairLens deliberately does not treat these gaps as proof of bias;
Model 7 is the demonstration that an income-only model can look unfair on
observational data while every counterfactual twin is unaffected.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)

from auditor.prober import Prober
from config_loader import REPO_ROOT, load_config
from eval.charts import grouped_bar
from eval.sandbox_runner import start_servers, stop_servers
from sandbox.generator import generate_applicants

RESULTS = REPO_ROOT / "eval" / "results"
ATTRIBUTES = ["gender", "pincode_group", "name_group", "age_band", "urban_rural"]


def _metric(value: Any) -> float | str:
    if value is None:
        return ""
    number = float(value)
    return "" if not np.isfinite(number) else round(number, 4)


def run_baseline(api_url: str, n: int, seed: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    applicants, labels = generate_applicants(n, seed=seed)
    prober = Prober(api_url, config)
    rows: list[dict[str, Any]] = []
    for model_id in range(1, 8):
        responses = prober.score_many_sync(model_id, applicants)
        approved = np.array([response.approved for response in responses], dtype=bool)
        truth = np.array(labels, dtype=bool)
        for attribute in ATTRIBUTES:
            sensitive = pd.Series([getattr(applicant, attribute) for applicant in applicants])
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


def write_outputs(rows: list[dict[str, Any]], seed: int) -> None:
    csv_path = RESULTS / "fairlearn.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    gender_rows = [row for row in rows if row["attribute"] == "gender"]
    grouped_bar(
        RESULTS / "fairlearn_gender.png",
        [f"Model {row['model_id']}" for row in gender_rows],
        [
            (
                "Demographic parity difference",
                [float(row["dp_difference"] or 0) for row in gender_rows],
                "#175cd3",
            ),
            (
                "Equalized odds difference",
                [float(row["eo_difference"] or 0) for row in gender_rows],
                "#b42318",
            ),
        ],
        title="Fairlearn observational baseline, gender (seed 42 sample)",
        ylabel="Difference (lower is not automatically fair)",
    )

    lines = [
        "# Fairlearn observational baseline",
        "",
        f"Sample: {rows[0]['n']} synthetic applicants, seed {seed}. The same "
        "applicants are scored by all seven models over HTTP. The labels are the "
        "generator's hidden repayment outcome, which a real auditor would not "
        "observe; this is an offline benchmark, not the FairLens audit.",
        "",
        "Demographic parity difference is the maximum approval-rate gap between "
        "groups. Equalized odds difference is the larger of the true-positive-rate "
        "and false-positive-rate gaps. Lower values are not proof of fairness: "
        "legitimate income differences can create both gaps.",
        "",
        "| Model | Attribute | DP difference | EO difference | Approval rates |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['model_id']} | {row['attribute']} | {row['dp_difference']} | "
            f"{row['eo_difference']} | {row['approval_rates']} |"
        )

    model7 = [row for row in gender_rows if row["model_id"] == 7][0]
    model2 = [row for row in gender_rows if row["model_id"] == 2][0]
    lines.extend(
        [
            "",
            "## Why this baseline is not enough",
            "",
            f"- Model 7 is income-only: its gender DP gap is "
            f"**{model7['dp_difference']}** and EO gap is "
            f"**{model7['eo_difference']}**, yet FairLens keeps **0** findings "
            "because gender/pincode/name twins never change its decision. The gap "
            "is explained by legitimate income differences in the generator.",
            f"- Model 2 has a planted gender penalty; fairlearn shows a gender DP "
            f"gap of **{model2['dp_difference']}**. FairLens also keeps the "
            "counterfactual gender finding and rejects the unrelated attributes.",
            "- These metrics use the hidden repayment label. In a real black-box "
            "procurement, the auditor usually cannot observe it; the twin design "
            "does not need it.",
            "",
            "Artifacts: `fairlearn.csv`, `fairlearn_gender.png`.",
            "",
        ]
    )
    (RESULTS / "fairlearn.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--api-url")
    args = parser.parse_args(argv)

    config = load_config()
    process = None
    if args.api_url:
        api_url = args.api_url.rstrip("/")
    else:
        processes, urls = start_servers(1)
        process = processes[0]
        api_url = urls[0]
    try:
        rows = run_baseline(api_url, args.n, args.seed, config)
        RESULTS.mkdir(parents=True, exist_ok=True)
        write_outputs(rows, args.seed)
        for row in rows:
            if row["attribute"] == "gender":
                print(
                    f"model {row['model_id']}: gender DP={row['dp_difference']} "
                    f"EO={row['eo_difference']}"
                )
        print(f"Wrote {RESULTS / 'fairlearn.md'} and {RESULTS / 'fairlearn.csv'}")
        return 0
    finally:
        if process is not None:
            stop_servers([process])


if __name__ == "__main__":
    raise SystemExit(main())
