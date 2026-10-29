"""Audit pipeline: plan -> probe -> statistics -> Skeptic -> impact -> report.

``run_audit`` is a generator. It yields ``AgentEvent`` objects for the live log
and returns an ``AuditReport``. Use ``collect_audit`` to drive it and capture the
return value.

The pipeline never imports sandbox scoring code. It uses the prober's HTTP
client and the applicant generator only.
"""

from __future__ import annotations

from typing import Any, Callable, Generator

from auditor.prober import CellProbe, Prober, ProbeResult
from auditor.interaction import (
    PlanTooLarge,
    build_search_plan,
    ensure_plan_fits,
    run_search,
)
from auditor.registry import load_registry
from auditor.skeptic import merge_redundant, review
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
from schemas import AgentEvent, AuditReport, Evidence, Finding, ProbeEvent
from targets.base import TargetAdapter

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
    if finding.kind == "generalized":
        # The affected subgroup is the treatment level inside the context.
        segment = {
            ("age_band" if key == "age" else key): value
            for key, value in finding.context.items()
        }
        treatment = finding.treatment or ""
        if treatment == "age":
            segment["age_band"] = finding.treatment_level or ""
        elif treatment:
            segment[treatment] = finding.treatment_level or ""
        return segment
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
    probe_event_sink: Callable[[list[ProbeEvent]], None] | None = None,
    target: TargetAdapter | None = None,
    sequential: bool | None = None,
    generalized: bool | None = None,
) -> Generator[AgentEvent, None, AuditReport]:
    seed = int(config.get("seed", 42) if seed is None else seed)
    cfg = config["audit"]
    alpha = float(cfg["alpha"])
    materiality = float(cfg["materiality"])
    min_pairs = int(cfg["min_pairs"])
    min_cell = int(cfg["min_cell_size"])
    iterations = int(cfg["bootstrap_iterations"])
    level = float(cfg["ci_level"])
    search_cfg = dict(cfg.get("search") or {})
    if generalized is None:
        generalized = bool(search_cfg.get("enabled", False))

    prober = Prober(
        api_url,
        config,
        pair_event_sink=probe_event_sink,
        target=target,
        sequential=sequential,
    )
    supported = (
        target.supported_probes if target is not None else frozenset(ATTRIBUTES)
        | {"intersectional"}
    )
    attributes = [attribute for attribute in ATTRIBUTES if attribute in supported]
    skipped = {
        probe: (
            getattr(target, "unsupported_details", {}).get(probe)
            or f"target {getattr(target, 'name', api_url)!r} does not support this probe"
        )
        for probe in (*ATTRIBUTES, "intersectional")
        if probe not in supported
    }
    if not attributes and not generalized:
        raise ValueError(
            "target supports none of the single-attribute probes "
            f"(supported={sorted(supported)})"
        )

    registry = None
    plan = None
    if generalized:
        registry = load_registry(config)
        supported_treatments = (
            sorted(target.supported_treatments)
            if target is not None
            else registry.treatment_attributes()
        )
        probe_cap = (
            int(getattr(target, "probe_cap", 0))
            if target is not None
            else int(config.get("targets", {}).get("probe_cap", 0))
        )
        plan = build_search_plan(
            config,
            registry,
            supported_treatments=supported_treatments,
            probe_cap=probe_cap,
            observational_applicants=int(config["data"]["n_observational"]),
        )
        yield _event(
            "planner",
            f"Generalized audit plan: {model_id} | {len(plan.cells)} cells "
            f"({len(plan.treatments)} treatments, exhaustive {plan.exhaustive_cells} "
            f"cells) | {plan.discovery_pairs:,} discovery pairs | "
            f"{plan.confirmation_reserve_pairs:,} confirmation-reserve pairs | "
            f"{plan.planned_applicants:,} applicants planned vs cap {plan.probe_cap:,} | "
            f"alpha={alpha} | materiality={materiality} | Holm",
            {"model_id": model_id, "seed": seed, "plan": plan.summary()},
        )
        try:
            ensure_plan_fits(plan)
        except PlanTooLarge as exc:
            yield _event(
                "planner",
                f"Audit aborted: {exc}",
                {"error": str(exc), "plan": plan.summary()},
            )
            raise
    else:
        yield _event(
            "planner",
            f"Audit plan: {model_id} | observational sample {config['data']['n_observational']} | "
            f"{cfg['n_pairs']} twins per single attribute | {cfg['intersectional_pairs_per_cell']} "
            f"per intersectional cell | alpha={alpha} | materiality={materiality} | Holm",
            {"model_id": model_id, "seed": seed},
        )
    if target is not None:
        yield _event(
            "planner",
            f"Target {target.name}: probes {sorted(supported)}; "
            f"skipped {sorted(skipped)}",
            {
                "target": target.name,
                "supported_probes": sorted(supported),
                "skipped_probes": skipped,
            },
        )
        for probe, reason in skipped.items():
            yield _event(
                "planner",
                f"Probe skipped: {probe} is not defined for target "
                f"{target.name}. {reason}",
                {"probe": probe, "skipped": True, "reason": reason},
            )
    seq_enabled = (
        sequential
        if sequential is not None
        else bool(cfg.get("sequential", {}).get("enabled", False))
    )
    if seq_enabled:
        seq_cfg = cfg.get("sequential", {})
        yield _event(
            "planner",
            f"Sequential stopping enabled: min_pairs={seq_cfg.get('min_pairs', 1000)}, "
            f"check_every={seq_cfg.get('check_every', 200)}; final inference uses "
            f"the fixed-sample McNemar/bootstrap on observed pairs",
            {"sequential": True, "config": seq_cfg},
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
    for attribute in attributes:
        table = observational_rates(obs_applicants, obs_responses, attribute)
        rates[attribute] = table
        target_group, comparison = choose_target_group(table)
        targets[attribute] = (target_group, comparison)
        gap = observational_gap(table, target_group, comparison, level)
        gaps[attribute] = gap
        yield _event(
            "statistician",
            f"Observational {ATTRIBUTE_LABELS[attribute]}: lowest group {target_group} "
            f"({table[target_group]['rate']:.1%}) vs {comparison} ({table[comparison]['rate']:.1%}); "
            f"gap {gap['gap']:+.3f} (95% CI {gap['ci_low']:+.3f} to {gap['ci_high']:+.3f})",
            {
                "attribute": attribute,
                "target": target_group,
                "comparison": comparison,
                "rates": table,
                "gap": gap,
            },
        )

    findings: list[Finding] = []
    search_summary: dict[str, Any] | None = None
    if generalized:
        assert plan is not None and registry is not None
        search_result = yield from run_search(
            prober,
            model_id,
            plan,
            config,
            seed,
            registry=registry,
            obs_applicants=obs_applicants,
            obs_responses=obs_responses,
        )
        findings = search_result.findings
        search_summary = search_result.summary
        all_inter = []
    else:
        # --- single-attribute counterfactual probes ---------------------------
        raw_singles: list[tuple[str, str, str, ProbeResult, Evidence, dict[str, float]]] = []
        for index, attribute in enumerate(attributes):
            target_group, comparison = targets[attribute]
            probe = prober.probe_attribute_sync(
                model_id=model_id,
                attribute=attribute,
                target_group=target_group,
                comparison_group=comparison,
                n=int(cfg["n_pairs"]),
                seed=seed + 1000 + index * 31,
            )
            for event in _drain(prober):
                yield event
            if probe.stopped_early:
                yield _event(
                    "statistician",
                    f"Sequential stop for {ATTRIBUTE_LABELS[attribute]}: "
                    f"{probe.n}/{probe.requested_n} pairs ({probe.stop_reason})",
                    {
                        "attribute": attribute,
                        "n": probe.n,
                        "requested_n": probe.requested_n,
                        "stop_reason": probe.stop_reason,
                        "b": probe.b,
                        "c": probe.c,
                    },
                )
            evidence = paired_evidence(
                probe.b,
                probe.c,
                probe.n,
                seed_key=f"single-{attribute}-{model_id}-{seed}",
                iterations=iterations,
                level=level,
            )
            raw_singles.append(
                (attribute, target_group, comparison, probe, evidence, gaps[attribute])
            )

        adjusted = holm_adjust([item[4].p_raw for item in raw_singles])
        singles: list[Finding] = []
        for (attribute, target_group, comparison, probe, evidence, gap), p_adj in zip(
            raw_singles, adjusted
        ):
            adjusted_evidence = evidence.model_copy(update={"p_adjusted": p_adj})
            finding = make_single_finding(
                attribute,
                target_group,
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
        all_inter: list[Finding] = []
        inter: list[Finding] = []
        if "intersectional" in supported:
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
            all_inter = make_intersectional_findings(
                cells_payload,
                obs_cells,
                iterations=iterations,
                level=level,
                alpha=alpha,
                top_k=None,
            )
            inter = all_inter[:5]
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
        else:
            yield _event(
                "statistician",
                "Intersectional scan skipped: the target has no urban/rural input, "
                "so the 12 gender x age x urban/rural cells are not defined.",
                {"probe": "intersectional", "skipped": True},
            )

        findings = singles + inter

    # --- Skeptic + income-matched re-tests --------------------------------
    for index, finding in enumerate(findings):
        matched_evidence: Evidence | None = None
        matched_bands: list[dict[str, Any]] | None = None
        if finding.kind == "generalized":
            if finding.status == "rejected":
                # An unconfirmed discovery candidate stays visible, with its
                # confirmation reason, but never becomes a bias claim.
                yield _event(
                    "skeptic",
                    f"REJECTED {finding.attribute_or_subgroup}: {finding.reason}",
                    {
                        "finding_id": finding.id,
                        "status": finding.status,
                        "checks": [],
                        "matched_evidence": None,
                    },
                )
                continue
            # Confirmation twins already hold income fixed; the income-band
            # breakdown is computed from the confirmation pairs, so no extra
            # probe is needed for this check.
            matched_evidence = finding.evidence
            matched_bands = finding.search.get("income_bands") or None
        else:
            required_n = min_cell if finding.kind == "intersectional" else min_pairs
            prefilter = (
                finding.evidence.n >= required_n
                and finding.evidence.p_adjusted < alpha
                and finding.evidence.net_flip_rate >= materiality
            )
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

    # --- redundancy: one primary finding per overlapping confirmed cell -----
    merges = merge_redundant(findings, config)
    for merge in merges:
        if merge["merged"] is None:
            yield _event(
                "skeptic",
                f"Redundancy check: {merge['reason']}",
                {
                    "primary": merge["primary"],
                    "checks": [merge["check"]],
                },
            )
        else:
            yield _event(
                "skeptic",
                f"MERGE {merge['merged']} -> {merge['primary']}: {merge['reason']}",
                {
                    "primary": merge["primary"],
                    "merged": merge["merged"],
                    "checks": [merge["check"]],
                },
            )
    if search_summary is not None:
        search_summary["merged"] = merges
        search_summary["kept_after_merge"] = [
            finding.id for finding in findings if finding.status == "kept"
        ]

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
    target_supports_mitigation = (
        target.supports_mitigation if target is not None else True
    )
    if include_mitigation and kept and not target_supports_mitigation:
        yield _event(
            "impact",
            "Mitigation curve skipped: this target does not expose the sandbox "
            "score-offset endpoint, so an offset sweep would not be comparable.",
            {"skipped": True, "reason": "target_does_not_support_mitigation"},
        )
    if include_mitigation and kept and target_supports_mitigation:
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
            "supported_probes": sorted(supported),
            "skipped_probes": skipped,
            "supported_treatments": (
                sorted(target.supported_treatments) if target is not None else None
            ),
            **( {"search": search_summary} if search_summary is not None else {}),
            "intersectional_cells": [
                {
                    "target_gender": f.target_group.split("|")[0],
                    "age_band": f.target_group.split("|")[1],
                    "urban_rural": f.target_group.split("|")[2],
                    "n": f.evidence.n,
                    "b": f.evidence.b,
                    "c": f.evidence.c,
                    "net_flip_rate": f.evidence.net_flip_rate,
                    "p_adjusted": f.evidence.p_adjusted,
                }
                for f in all_inter
            ],
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
