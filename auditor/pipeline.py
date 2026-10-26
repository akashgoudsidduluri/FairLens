"""Audit pipeline: plan -> probe -> statistics -> Skeptic -> impact -> report.

``run_audit`` is a generator. It yields ``AgentEvent`` objects for the live log
and returns an ``AuditReport``. Use ``collect_audit`` to drive it and capture the
return value.

The pipeline never imports sandbox scoring code. It uses the prober's HTTP
client and the applicant generator only.
"""

from __future__ import annotations

from typing import Any, Generator

from auditor.prober import CellProbe, Prober, ProbeResult
from auditor.skeptic import review
from auditor.statistician import (
    choose_target_group,
    holm_adjust,
    intersectional_observational_rates,
    make_intersectional_findings,
    make_single_finding,
    observational_gap,
    observational_rates,
    paired_evidence,
)
from impact.impact import impact_per_10k
from schemas import AgentEvent, AuditReport, Evidence, Finding

ATTRIBUTES = ("gender", "pincode_group", "name_group")
ATTRIBUTE_LABELS = {
    "gender": "gender",
    "pincode_group": "pincode group",
    "name_group": "name group",
}


def _event(agent: str, message: str, payload: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(agent=agent, message=message, payload=payload or {})


def _drain(prober: Prober) -> list[AgentEvent]:
    return prober.drain_events()


def _segment_for(finding: Finding) -> dict[str, str]:
    if finding.kind == "single_attribute":
        attribute = finding.attribute_or_subgroup.split("=", 1)[0]
        return {attribute: finding.target_group}
    gender, age_band, urban_rural = finding.target_group.split("|")
    return {
        "gender": gender,
        "age_band": age_band,
        "urban_rural": urban_rural,
    }


def run_audit(
    model_id: int,
    api_url: str,
    config: dict[str, Any],
    seed: int | None = None,
    *,
    include_mitigation: bool = True,
    include_narrative: bool = True,
) -> Generator[AgentEvent, None, AuditReport]:
    seed = int(config.get("seed", 42) if seed is None else seed)
    cfg = config["audit"]
    alpha = float(cfg["alpha"])
    materiality = float(cfg["materiality"])
    min_pairs = int(cfg["min_pairs"])
    min_cell = int(cfg["min_cell_size"])
    iterations = int(cfg["bootstrap_iterations"])
    level = float(cfg["ci_level"])

    prober = Prober(api_url, config)
    yield _event(
        "planner",
        f"Audit plan: {model_id} | observational sample {config['data']['n_observational']} | "
        f"{cfg['n_pairs']} twins per single attribute | {cfg['intersectional_pairs_per_cell']} "
        f"per intersectional cell | alpha={alpha} | materiality={materiality} | Holm",
        {"model_id": model_id, "seed": seed},
    )

    try:
        prober.check_health_sync()
    except Exception as exc:  # noqa: BLE001
        yield _event("planner", f"Audit aborted: {exc}", {"error": str(exc)})
        raise
    for event in _drain(prober):
        yield event

    obs_applicants, obs_responses = prober.sample_observational_sync(
        model_id, int(config["data"]["n_observational"]), seed
    )
    for event in _drain(prober):
        yield event

    rates: dict[str, dict[str, dict[str, float]]] = {}
    targets: dict[str, tuple[str, str]] = {}
    gaps: dict[str, dict[str, float]] = {}
    for attribute in ATTRIBUTES:
        table = observational_rates(obs_applicants, obs_responses, attribute)
        rates[attribute] = table
        target, comparison = choose_target_group(table)
        targets[attribute] = (target, comparison)
        gap = observational_gap(table, target, comparison, level)
        gaps[attribute] = gap
        yield _event(
            "statistician",
            f"Observational {ATTRIBUTE_LABELS[attribute]}: lowest group {target} "
            f"({table[target]['rate']:.1%}) vs {comparison} ({table[comparison]['rate']:.1%}); "
            f"gap {gap['gap']:+.3f} (95% CI {gap['ci_low']:+.3f} to {gap['ci_high']:+.3f})",
            {
                "attribute": attribute,
                "target": target,
                "comparison": comparison,
                "rates": table,
                "gap": gap,
            },
        )

    # --- single-attribute counterfactual probes ---------------------------
    raw_singles: list[tuple[str, str, str, ProbeResult, Evidence, dict[str, float]]] = []
    for index, attribute in enumerate(ATTRIBUTES):
        target, comparison = targets[attribute]
        probe = prober.probe_attribute_sync(
            model_id=model_id,
            attribute=attribute,
            target_group=target,
            comparison_group=comparison,
            n=int(cfg["n_pairs"]),
            seed=seed + 1000 + index * 31,
        )
        for event in _drain(prober):
            yield event
        evidence = paired_evidence(
            probe.b,
            probe.c,
            probe.n,
            seed_key=f"single-{attribute}-{model_id}-{seed}",
            iterations=iterations,
            level=level,
        )
        raw_singles.append((attribute, target, comparison, probe, evidence, gaps[attribute]))

    adjusted = holm_adjust([item[4].p_raw for item in raw_singles])
    singles: list[Finding] = []
    for (attribute, target, comparison, probe, evidence, gap), p_adj in zip(
        raw_singles, adjusted
    ):
        adjusted_evidence = evidence.model_copy(update={"p_adjusted": p_adj})
        finding = make_single_finding(
            attribute,
            target,
            comparison,
            adjusted_evidence,
            rates[attribute],
            gap,
        )
        singles.append(finding)
        yield _event(
            "statistician",
            f"{ATTRIBUTE_LABELS[attribute]} candidate: {probe.b} harmed / {probe.c} helped "
            f"of {probe.n}; net {evidence.net_flip_rate:+.4f}; "
            f"Holm p={p_adj:.2e}",
            {
                "finding_id": finding.id,
                "b": probe.b,
                "c": probe.c,
                "n": probe.n,
                "net_flip_rate": evidence.net_flip_rate,
                "p_adjusted": p_adj,
            },
        )

    # --- intersectional scan ---------------------------------------------
    cell_probes: list[CellProbe] = prober.probe_intersectional_sync(
        model_id, int(cfg["intersectional_pairs_per_cell"]), seed + 9000
    )
    for event in _drain(prober):
        yield event
    obs_cells = intersectional_observational_rates(obs_applicants, obs_responses)
    cells_payload = [
        {
            "target_gender": c.target_gender,
            "comparison_gender": c.comparison_gender,
            "age_band": c.age_band,
            "urban_rural": c.urban_rural,
            "n": c.n,
            "b": c.b,
            "c": c.c,
        }
        for c in cell_probes
    ]
    inter = make_intersectional_findings(
        cells_payload,
        obs_cells,
        iterations=iterations,
        level=level,
        alpha=alpha,
        top_k=5,
    )
    for finding in inter:
        yield _event(
            "statistician",
            f"Intersectional {finding.attribute_or_subgroup}: net "
            f"{finding.evidence.net_flip_rate:+.4f}, Holm p="
            f"{finding.evidence.p_adjusted:.2e}",
            {
                "finding_id": finding.id,
                "net_flip_rate": finding.evidence.net_flip_rate,
                "p_adjusted": finding.evidence.p_adjusted,
            },
        )

    findings: list[Finding] = singles + inter

    # --- Skeptic + income-matched re-tests --------------------------------
    for index, finding in enumerate(findings):
        required_n = min_cell if finding.kind == "intersectional" else min_pairs
        prefilter = (
            finding.evidence.n >= required_n
            and finding.evidence.p_adjusted < alpha
            and finding.evidence.net_flip_rate >= materiality
        )
        matched_evidence: Evidence | None = None
        matched_bands: list[dict[str, Any]] | None = None
        if prefilter:
            if finding.kind == "single_attribute":
                matched_probe = prober.matched_retest_sync(
                    model_id=model_id,
                    attribute=finding.attribute_or_subgroup.split("=", 1)[0],
                    target_group=finding.target_group,
                    comparison_group=finding.comparison_group,
                    n=int(cfg["matched_n_pairs"]),
                    seed=seed + 5000 + index * 17,
                )
            else:
                gender, age_band, urban_rural = finding.target_group.split("|")
                matched_probe = prober.matched_retest_sync(
                    model_id=model_id,
                    attribute="gender",
                    target_group=gender,
                    comparison_group=finding.comparison_group.split("|", 1)[0],
                    n=int(cfg["matched_n_pairs"]),
                    seed=seed + 5000 + index * 17,
                    age_band=age_band,
                    urban_rural=urban_rural,
                )
            for event in _drain(prober):
                yield event
            matched_evidence = paired_evidence(
                matched_probe.b,
                matched_probe.c,
                matched_probe.n,
                seed_key=f"matched-{finding.id}-{model_id}-{seed}",
                iterations=iterations,
                level=level,
            )
            matched_bands = matched_probe.bands

        verdict = review(finding, config, matched_evidence, matched_bands)
        finding.status = verdict.final_status  # type: ignore[assignment]
        finding.reason = verdict.reason
        finding.matched_evidence = matched_evidence
        yield _event(
            "skeptic",
            f"{finding.status.upper()} {finding.attribute_or_subgroup}: {verdict.reason}",
            {
                "finding_id": finding.id,
                "status": finding.status,
                "checks": [check.model_dump() for check in verdict.checks],
                "matched_evidence": (
                    matched_evidence.model_dump() if matched_evidence else None
                ),
            },
        )

    kept = [f for f in findings if f.status == "kept"]
    impact = [impact_per_10k(f) for f in kept]
    for estimate in impact:
        yield _event(
            "impact",
            f"{estimate.subgroup}: about {estimate.per_10k:,.0f} people per 10,000 "
            f"(95% range {estimate.ci_low_per_10k:,.0f}–{estimate.ci_high_per_10k:,.0f})",
            estimate.model_dump(),
        )

    mitigation_curve: list[dict[str, Any]] = []
    if include_mitigation and kept:
        primary = max(kept, key=lambda f: f.evidence.net_flip_rate)
        try:
            from impact.mitigate import build_curve

            mitigation_curve = build_curve(
                model_id=model_id,
                api_url=api_url,
                segment=_segment_for(primary),
                config=config,
                seed=seed + 31_000,
            )
            yield _event(
                "impact",
                f"Mitigation sweep for {primary.attribute_or_subgroup}: "
                f"{len(mitigation_curve)} offset points",
                {"curve": mitigation_curve, "finding_id": primary.id},
            )
        except Exception as exc:  # noqa: BLE001
            yield _event(
                "impact",
                f"Mitigation curve unavailable: {exc}",
                {"error": str(exc)},
            )

    report = AuditReport(
        model_id=model_id,
        config=config,
        findings=findings,
        impact=impact,
        mitigation_curve=mitigation_curve,
        observational={
            "rates": rates,
            "targets": {k: {"target": v[0], "comparison": v[1]} for k, v in targets.items()},
            "gaps": gaps,
            "n_observational": len(obs_applicants),
        },
    )

    if include_narrative:
        try:
            from report.number_check import check_numbers
            from report.reporter import build_payload, generate_narrative

            payload = build_payload(report)
            narrative_result = generate_narrative(payload, config)
            report.narrative = narrative_result["narrative"]
            check = check_numbers(report.narrative, payload)
            report.number_check_result = {
                **check,
                "source": narrative_result.get("source", "unknown"),
            }
            yield _event(
                "reporter",
                f"Narrative written from computed JSON ({narrative_result.get('source', '?')}); "
                f"number check {'PASSED' if check['passed'] else 'FAILED'}",
                report.number_check_result,
            )
        except Exception as exc:  # noqa: BLE001
            yield _event("reporter", f"Narrative unavailable: {exc}", {"error": str(exc)})

    yield _event(
        "planner",
        f"Audit complete: {len(kept)} kept, "
        f"{sum(1 for f in findings if f.status == 'immaterial')} immaterial, "
        f"{sum(1 for f in findings if f.status == 'rejected')} rejected",
        {
            "model_id": model_id,
            "kept": len(kept),
            "findings": len(findings),
        },
    )
    return report


def collect_audit(
    model_id: int,
    api_url: str,
    config: dict[str, Any],
    seed: int | None = None,
    **kwargs: Any,
) -> tuple[list[AgentEvent], AuditReport]:
    """Drive ``run_audit`` and return (events, report)."""

    generator = run_audit(model_id, api_url, config, seed, **kwargs)
    events: list[AgentEvent] = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value
