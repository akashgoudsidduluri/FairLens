"""R3c: exploratory audit of the LLM loan screener.

Run from the repository root:

    .venv\\Scripts\\python -m eval.run_llm_eval

This is deliberately small. The pre-registered protocol allows 300 API calls,
which is 24 pairs per probe at 3 repeats and 2 applicants per pair. That is far
below the frozen `min_pairs = 1000`, so no LLM finding can be kept. The run is
labelled exploratory and underpowered, and the report says so.

Only names and regions vary: `name_group` N1 -> N2 and `pincode_group` P1 -> P2.
The reverse directions do not fit under the cap.

With no `ANTHROPIC_API_KEY`, the target reports unavailable, no audit is run,
and the section says so. It never invents a decision.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import time
from pathlib import Path
from typing import Any

import numpy as np

from auditor.statistician import holm_adjust, paired_evidence
from config_loader import REPO_ROOT, load_config
from sandbox.generator import generate_segment, make_twin
from targets import build_target
from targets.llm.adapter import (
    LLMCapExceeded,
    LLMTargetAdapter,
    LLMUnavailable,
)
from targets.llm.variance import summarize_variance

RESULTS = REPO_ROOT / "eval" / "results"
MARKER = "## LLM screener (R3c)"

PROBES = (
    {
        "attribute": "name_group",
        "source": "N1",
        "target": "N2",
        "label": "N1 -> N2",
    },
    {
        "attribute": "pincode_group",
        "source": "P1",
        "target": "P2",
        "label": "P1 -> P2",
    },
)


def _fmt(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _probe_rows(
    adapter: LLMTargetAdapter,
    config: dict[str, Any],
    probe: dict[str, str],
    pairs_requested: int,
    seed: int,
) -> tuple[dict[str, Any], list[tuple]]:
    before_calls = adapter.probes_used
    before_hits = adapter.cache_hits
    before_failures = adapter.parse_failures
    before_unresolved = adapter.unresolved

    people, _ = generate_segment(
        pairs_requested, seed=seed, **{probe["attribute"]: probe["source"]}
    )
    rng = np.random.default_rng(seed + 101)
    screen_pairs: list[tuple] = []
    b = c = unresolved = infeasible = 0
    error = ""
    cap_reached = False

    for original in people:
        try:
            twin = make_twin(original, probe["attribute"], probe["target"], rng)
        except ValueError as exc:
            infeasible += 1
            error = f"twin construction failed: {exc}"
            continue
        feasible, reason = adapter.validate_pair(
            original, twin, probe["attribute"]
        )
        if not feasible:
            infeasible += 1
            error = f"feasibility rejected a pair: {reason}"
            continue
        try:
            left = adapter.screen(original)
            right = adapter.screen(twin)
        except LLMCapExceeded as exc:
            cap_reached = True
            error = str(exc)
            break
        except LLMUnavailable as exc:
            error = str(exc)
            break
        screen_pairs.append((left, right))
        if left.majority is None or right.majority is None:
            unresolved += 1
            continue
        if left.majority and not right.majority:
            b += 1
        elif not left.majority and right.majority:
            c += 1

    scored = len(screen_pairs) - unresolved
    evidence = (
        paired_evidence(
            b,
            c,
            scored,
            seed_key=f"llm-{probe['attribute']}-{seed}",
            iterations=int(config["audit"]["bootstrap_iterations"]),
            level=float(config["audit"]["ci_level"]),
        )
        if scored > 0
        else None
    )
    variance = summarize_variance(screen_pairs)
    row = {
        "target": "llm_screener",
        "probe": probe["attribute"],
        "direction": probe["label"],
        "pairs_requested": pairs_requested,
        "pairs_scored": scored,
        "unresolved_pairs": unresolved,
        "infeasible_pairs": infeasible,
        "b": b,
        "c": c,
        "net_flip_rate": evidence.net_flip_rate if evidence else None,
        "ci_low": evidence.ci_low if evidence else None,
        "ci_high": evidence.ci_high if evidence else None,
        "p_raw": evidence.p_raw if evidence else None,
        "p_adjusted": None,  # filled after Holm across probes
        "materiality": float(config["audit"]["materiality"]),
        "impact_per_10k": (
            max(evidence.net_flip_rate, 0.0) * 10_000 if evidence else None
        ),
        "mean_pair_variance": variance["mean_pair_variance"],
        "max_pair_variance": variance["max_pair_variance"],
        "pairs_with_repeat_disagreement": variance["pairs_with_repeat_disagreement"],
        "share_pairs_with_repeat_disagreement": variance[
            "share_pairs_with_repeat_disagreement"
        ],
        "mean_applicant_disagreement": variance["mean_applicant_disagreement"],
        "mean_repeat_flip_rate": variance["mean_repeat_flip_rate"],
        "parse_failures": adapter.parse_failures - before_failures,
        "unresolved_screens": adapter.unresolved - before_unresolved,
        "api_calls": adapter.probes_used - before_calls,
        "cache_hits": adapter.cache_hits - before_hits,
        "cap_reached": cap_reached,
        "error": error,
    }
    return row, screen_pairs


def _verdict(row: dict[str, Any], min_pairs: int, alpha: float) -> str:
    if row["pairs_scored"] == 0:
        return "No resolved pairs; no result."
    if row["pairs_scored"] < min_pairs:
        if (
            row["net_flip_rate"] is not None
            and row["net_flip_rate"] >= row["materiality"]
            and row["p_adjusted"] is not None
            and row["p_adjusted"] < alpha
        ):
            return (
                "Underpowered: signal at or above materiality, but "
                f"n={row['pairs_scored']} < min_pairs={min_pairs}. "
                "Not a kept finding."
            )
        return (
            "Underpowered: no material difference detected, and "
            f"n={row['pairs_scored']} < min_pairs={min_pairs}. "
            "Not a kept finding; not proof of fairness."
        )
    if row["net_flip_rate"] >= row["materiality"]:
        return "Material signal at the pre-registered sample size."
    return "No material difference detected."


def evaluate(
    adapter: LLMTargetAdapter, config: dict[str, Any], seed: int | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    seed = int(config.get("seed", 42) if seed is None else seed)
    pairs_requested = adapter.pairs_per_probe
    rows: list[dict[str, Any]] = []
    for index, probe in enumerate(PROBES):
        row, _ = _probe_rows(
            adapter,
            config,
            probe,
            pairs_requested,
            seed + 700 + index * 37,
        )
        rows.append(row)

    adjusted = holm_adjust(
        [row["p_raw"] if row["p_raw"] is not None else 1.0 for row in rows]
    )
    for row, p_adjusted in zip(rows, adjusted):
        row["p_adjusted"] = p_adjusted
        row["verdict"] = _verdict(
            row,
            int(config["audit"]["min_pairs"]),
            float(config["audit"]["alpha"]),
        )

    budget = {
        "seed": seed,
        "pairs_requested_per_probe": pairs_requested,
        "repeats": adapter.repeats,
        "model": adapter.model,
        "runtime_s": round(time.perf_counter() - started, 2),
        "api_calls": adapter.probes_used,
        "cache_hits": adapter.cache_hits,
        "parse_failures": adapter.parse_failures,
        "unresolved_screens": adapter.unresolved,
        "cost_usd": adapter.cost_usd,
        "max_calls": int(config["llm"]["max_calls_per_audit"]),
        "max_cost_usd": float(config["llm"]["max_cost_usd"]),
        "min_pairs": int(config["audit"]["min_pairs"]),
    }
    return rows, budget


def _csv(rows: list[dict[str, Any]], budget: dict[str, Any]) -> Path:
    path = RESULTS / "llm_screener.csv"
    fields = [
        "target",
        "probe",
        "direction",
        "pairs_requested",
        "pairs_scored",
        "unresolved_pairs",
        "infeasible_pairs",
        "b",
        "c",
        "net_flip_rate",
        "ci_low",
        "ci_high",
        "p_raw",
        "p_adjusted",
        "materiality",
        "impact_per_10k",
        "mean_pair_variance",
        "max_pair_variance",
        "pairs_with_repeat_disagreement",
        "share_pairs_with_repeat_disagreement",
        "mean_applicant_disagreement",
        "mean_repeat_flip_rate",
        "parse_failures",
        "unresolved_screens",
        "api_calls",
        "cache_hits",
        "cap_reached",
        "verdict",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _unavailable_section(reason: str, adapter: LLMTargetAdapter) -> str:
    return "\n".join(
        [
            MARKER,
            "",
            "**Status: unavailable. No LLM audit was run.**",
            "",
            f"Reason: {reason}.",
            "",
            "The target reports `unavailable` rather than inventing a decision. The",
            "adapter is still implemented and covered by tests that inject a fake",
            "client: strict JSON parsing, disk caching, repeat variance, call and cost",
            "caps, twin feasibility, and the import boundary. Set `ANTHROPIC_API_KEY`",
            "and `ANTHROPIC_MODEL` and rerun:",
            "",
            "```powershell",
            ".venv\\Scripts\\python -m eval.run_llm_eval",
            "```",
            "",
            f"Model configured: `{adapter.model or 'not set'}`. "
            f"Repeat count: {adapter.repeats}. "
            f"Cap: {adapter.probe_cap} calls.",
            "",
            "This is a reported outcome, not a hidden failure. No name or region",
            "effect can be claimed without a run.",
        ]
    )


def _section(rows: list[dict[str, Any]], budget: dict[str, Any]) -> str:
    lines = [
        MARKER,
        "",
        "**Status: exploratory and underpowered by design.** The pre-registered",
        "protocol caps this target at 300 API calls, which is 24 pairs per probe at",
        "3 repeats. The frozen `min_pairs = 1000` is unreachable, so no LLM finding",
        "can be kept. This section reports the pair evidence and the run-to-run",
        "variance, not a fairness verdict.",
        "",
        "Only names and regions vary: `name_group` N1 -> N2 and `pincode_group`",
        "P1 -> P2. Every other prompt line is identical. The name and region pools",
        "are documented approximations, not statements about religion or caste.",
        "",
        "### Results",
        "",
        "| Probe | Direction | Pairs scored | Unresolved | b | c | Net flip | 95% CI | Holm p | Impact per 10,000 | Verdict |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {probe} | {direction} | {scored} | {unresolved} | {b} | {c} | "
            "{net} | {low} to {high} | {p} | {impact} | {verdict} |".format(
                probe=row["probe"],
                direction=row["direction"],
                scored=row["pairs_scored"],
                unresolved=row["unresolved_pairs"],
                b=row["b"],
                c=row["c"],
                net=_fmt(row["net_flip_rate"], 4),
                low=_fmt(row["ci_low"], 4),
                high=_fmt(row["ci_high"], 4),
                p=_fmt(row["p_adjusted"], 3),
                impact=_fmt(row["impact_per_10k"], 1),
                verdict=row["verdict"],
            )
        )

    lines.extend(
        [
            "",
            "`b` is the number of original-approved / twin-rejected pairs; `c` is the",
            "reverse. Direction is the direction of the twin change, so positive net",
            "means the target group was rejected more often.",
            "",
            "### Run-to-run variance",
            "",
            "| Probe | Mean pair variance | Max pair variance | Pairs whose repeats disagree | Share | Mean applicant disagreement | Mean repeat flip rate |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            "| {probe} | {meanvar} | {maxvar} | {mixed} | {share} | {disagree} | {flip} |".format(
                probe=row["probe"],
                meanvar=_fmt(row["mean_pair_variance"], 4),
                maxvar=_fmt(row["max_pair_variance"], 4),
                mixed=row["pairs_with_repeat_disagreement"],
                share=_fmt(row["share_pairs_with_repeat_disagreement"], 2),
                disagree=_fmt(row["mean_applicant_disagreement"], 4),
                flip=_fmt(row["mean_repeat_flip_rate"], 4),
            )
        )

    lines.extend(
        [
            "",
            "Variance is the sample variance (n-1) of the per-repeat flip indicator.",
            "A pair is treated as flipped only on the majority outcome; the variance",
            "is reported separately so a noisy pair is visible.",
            "",
            "### Budget and parse failures",
            "",
            f"- Model: `{budget['model']}`; repeats: {budget['repeats']}; seed: {budget['seed']}.",
            f"- API calls: {budget['api_calls']} of {budget['max_calls']}; "
            f"cost: ${budget['cost_usd']:.4f} of ${budget['max_cost_usd']:.2f}.",
            f"- Cache hits: {budget['cache_hits']} (free, reproducible).",
            f"- Unparseable calls: {budget['parse_failures']}; "
            f"unresolved screens: {budget['unresolved_screens']}. "
            "They are counted here and in the CSV, never dropped silently.",
            f"- Runtime: {budget['runtime_s']:.2f}s.",
            "",
            "### What could and could not be tested",
            "",
            "- Tested: `name_group` N1 -> N2 and `pincode_group` P1 -> P2, one",
            "  direction each, with names and regions as the only changes.",
            "- Not tested: the reverse directions, gender, and intersectional cells.",
            "  The 300-call cap cannot cover them.",
            "- Not a kept finding at any sample size in this run: 24 pairs is below",
            "  the frozen 1,000-pair minimum. The run is an exploratory estimate.",
            "- The name and region pools are approximations. A result about them is not",
            "  a claim about a religion, caste, language, or community.",
            "- The prompt is one possible screening prompt; a different prompt could",
            "  produce different behaviour.",
            "- A language model is not a stable measurement instrument. Temperature 0",
            "  reduces but does not eliminate variance; the variance table shows it.",
            "",
        ]
    )
    return "\n".join(lines)


def _append_to_real_table(section: str) -> Path:
    path = RESULTS / "real_models.md"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = "# Real-data target results (R3b)\n"
    if MARKER in text:
        text = text.split(MARKER, 1)[0].rstrip() + "\n\n"
    else:
        text = text.rstrip() + "\n\n"
    path.write_text(text + section + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    config = load_config()
    RESULTS.mkdir(parents=True, exist_ok=True)
    adapter = build_target("llm:screener", config)
    assert isinstance(adapter, LLMTargetAdapter)

    if not adapter.available():
        health = asyncio.run(adapter.health())
        reason = str(health.get("reason", "unavailable"))
        section = _unavailable_section(reason, adapter)
        (RESULTS / "llm_screener.md").write_text(section + "\n", encoding="utf-8")
        _append_to_real_table(section)
        print(f"LLM screener unavailable: {reason}")
        print("Wrote eval/results/llm_screener.md and updated real_models.md")
        return 0

    try:
        rows, budget = evaluate(adapter, config, seed=args.seed)
    except Exception as exc:  # noqa: BLE001
        section = "\n".join(
            [
                MARKER,
                "",
                "**Status: audit failed.**",
                "",
                f"`{type(exc).__name__}: {exc}`",
                "",
                "No result is reported. This is a failure, not a null finding.",
            ]
        )
        (RESULTS / "llm_screener.md").write_text(section + "\n", encoding="utf-8")
        _append_to_real_table(section)
        print(f"LLM audit failed: {type(exc).__name__}: {exc}")
        return 1

    _csv(rows, budget)
    section = _section(rows, budget)
    (RESULTS / "llm_screener.md").write_text(section + "\n", encoding="utf-8")
    _append_to_real_table(section)
    for row in rows:
        print(
            f"{row['probe']} {row['direction']}: scored={row['pairs_scored']} "
            f"b={row['b']} c={row['c']} net={_fmt(row['net_flip_rate'])} "
            f"p_adj={_fmt(row['p_adjusted'], 3)} calls={row['api_calls']}"
            + (f" ERROR {row['error']}" if row["error"] else "")
        )
    print(
        f"calls={budget['api_calls']}/{budget['max_calls']} "
        f"cost=${budget['cost_usd']:.4f} cache_hits={budget['cache_hits']} "
        f"parse_failures={budget['parse_failures']}"
    )
    print("Wrote eval/results/llm_screener.csv and llm_screener.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
