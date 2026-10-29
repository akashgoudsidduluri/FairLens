"""Interaction search with discover-then-confirm (R5 Step 3).

The old auditor conflated the *treatment* (the attribute flipped between twins)
with the *context* (the subgroup where the effect appears). This module keeps
them separate:

    treatment = gender female      (the only signal that changes)
    context   = {age: 45+, urban_rural: rural, name_group: N2}

Phases
------
**Phase A (discovery)** probes the pre-registered panel once: a main effect per
treatment level, every depth-1 context cell, and the deep panel from
``config.yaml``. Every examined cell enters one Holm family. Cells below
``min_cell_size`` are reported as not testable and are not tested.

**Phase B (confirmation)** sends *fresh* twins (a new seed stream, therefore new
applicants) only to discovery candidates. A candidate is confirmed only when
``p_raw < alpha / m`` (the most conservative Holm threshold, with ``m`` the
number of tested discovery cells), the net flip is at least ``materiality``, and
the direction is unchanged. Only confirmed cells can become findings.

The plan is costed before any request. If the planned applicant count exceeds
the target's hard probe cap, ``ensure_plan_fits`` raises ``PlanTooLarge`` with
the planned count shown; the sample is never shrunk silently.

Everything here is black-box: the caller passes a ``Prober``, which talks HTTP
or a target adapter. No scoring code is imported.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from typing import Any, Generator, Sequence

import numpy as np

from auditor.prober import CellProbeResult, CellSpec, Prober
from auditor.registry import AttributeRegistry, minimum_detectable_effect
from auditor.statistician import (
    holm_adjust,
    mcnemar_exact,
    newcombe_gap_ci,
    paired_evidence,
)
from sandbox.generator import income_band_boundaries
from schemas import AgentEvent, Applicant, Finding, ModelResponse


class PlanTooLarge(RuntimeError):
    """Raised when the pre-registered search plan exceeds the probe cap."""


# --------------------------------------------------------------------------- plan
@dataclass(frozen=True)
class SearchCell(CellSpec):
    """A treatment level inside a context cell, plus its discovery provenance."""

    depth: int = 0
    source: str = "main"

    @property
    def cell_id(self) -> str:
        parts = [self.treatment, self.level]
        parts.extend(f"{key}={value}" for key, value in self.context.items())
        return "|".join(parts)

    @property
    def label(self) -> str:
        base = f"{self.treatment}={self.level} vs {self.comparison}"
        if not self.context:
            return f"{base} (main effect)"
        context = ", ".join(f"{key}={value}" for key, value in self.context.items())
        return f"{base} in {context}"


@dataclass(frozen=True)
class SearchPlan:
    cells: tuple[SearchCell, ...]
    treatments: tuple[str, ...]
    skipped_treatments: dict[str, str]
    exhaustive_cells: int
    exhaustive_pairs: int
    discovery_pairs: int
    confirmation_reserve_pairs: int
    observational_applicants: int
    planned_applicants: int
    probe_cap: int
    min_cell_size: int
    confirmation_pairs: int
    max_candidates: int

    def summary(self) -> dict[str, Any]:
        by_source: dict[str, int] = {}
        for cell in self.cells:
            by_source[cell.source] = by_source.get(cell.source, 0) + 1
        return {
            "treatments": list(self.treatments),
            "skipped_treatments": dict(self.skipped_treatments),
            "cells": len(self.cells),
            "cells_by_source": by_source,
            "exhaustive_cells": self.exhaustive_cells,
            "exhaustive_applicants": 2 * self.exhaustive_pairs,
            "discovery_pairs": self.discovery_pairs,
            "confirmation_reserve_pairs": self.confirmation_reserve_pairs,
            "observational_applicants": self.observational_applicants,
            "planned_applicants": self.planned_applicants,
            "probe_cap": self.probe_cap,
            "min_cell_size": self.min_cell_size,
            "confirmation_pairs": self.confirmation_pairs,
            "max_confirmation_candidates": self.max_candidates,
        }


def _choices(registry: AttributeRegistry, name: str) -> tuple[str, ...]:
    spec = registry.get(name)
    return spec.values if spec.type == "categorical" else spec.labels


def _context_count(
    registry: AttributeRegistry, contexts: Sequence[str], max_depth: int
) -> int:
    total = 0
    for depth in range(1, max_depth + 1):
        for combo in itertools.combinations(contexts, depth):
            product = 1
            for name in combo:
                product *= len(_choices(registry, name))
            total += product
    return total


def build_search_plan(
    config: dict[str, Any],
    registry: AttributeRegistry,
    *,
    supported_treatments: Sequence[str] | None = None,
    probe_cap: int = 0,
    observational_applicants: int | None = None,
) -> SearchPlan:
    """Build the pre-registered discovery panel and cost it.

    ``supported_treatments`` comes from the target. A treatment the target does
    not support is skipped with a reason, exactly like an unsupported probe.
    """

    search = dict(config.get("audit", {}).get("search") or {})
    if not search:
        raise ValueError("generalized search needs config.audit.search")
    max_depth = int(search.get("max_context_depth", 3))
    main_pairs = int(search.get("main_effect_pairs", 1000))
    cell_pairs = int(search.get("cell_pairs", 200))
    confirmation_pairs = int(search.get("confirmation_pairs", 400))
    max_candidates = int(search.get("max_confirmation_candidates", 16))
    min_cell = int(search.get("min_cell_size", config["audit"]["min_cell_size"]))
    if max_depth < 1:
        raise ValueError("max_context_depth must be at least 1")
    if min(main_pairs, cell_pairs, confirmation_pairs) < min_cell:
        raise ValueError(
            "main_effect_pairs, cell_pairs and confirmation_pairs must each be "
            f"at least min_cell_size ({min_cell})"
        )
    if observational_applicants is None:
        observational_applicants = int(config["data"]["n_observational"])

    supported = (
        set(registry.treatment_attributes())
        if supported_treatments is None
        else set(supported_treatments) & set(registry.treatment_attributes())
    )
    skipped: dict[str, str] = {}
    for treatment in registry.treatment_attributes():
        if treatment not in supported:
            skipped[treatment] = "target does not support this treatment"

    deep_panel = search.get("deep_panel") or {}
    cells: list[SearchCell] = []
    seen: set[str] = set()
    treatments: list[str] = []
    exhaustive_cells = 0
    exhaustive_pairs = 0

    for treatment in registry.treatment_attributes():
        if treatment not in supported:
            continue
        spec = registry.get(treatment)
        contexts = registry.context_attributes(treatment)
        context_count = _context_count(registry, contexts, max_depth)
        levels = list(spec.treatment_levels)
        highest = levels[-1]
        treatments.append(treatment)

        for level in levels:
            exhaustive_cells += 1 + context_count
            exhaustive_pairs += main_pairs + context_count * cell_pairs
            cells.append(
                SearchCell(
                    treatment=treatment,
                    level=level,
                    comparison=str(spec.comparison_level),
                    context={},
                    pairs=main_pairs,
                    depth=0,
                    source="main",
                )
            )
            if level != highest:
                # The full context panel is registered at the highest level
                # only; lower levels get a main-effect probe (pre-registration).
                continue
            for name in contexts:
                for value in _choices(registry, name):
                    cells.append(
                        SearchCell(
                            treatment=treatment,
                            level=level,
                            comparison=str(spec.comparison_level),
                            context={name: value},
                            pairs=cell_pairs,
                            depth=1,
                            source="depth1",
                        )
                    )
            for entry in deep_panel.get(treatment) or []:
                context = {str(key): str(value) for key, value in entry.items()}
                if treatment in context:
                    raise ValueError(
                        f"deep panel for {treatment} cannot use the treatment as context"
                    )
                if not 1 <= len(context) <= max_depth:
                    raise ValueError(
                        f"deep panel for {treatment} has depth {len(context)} "
                        f"outside 1..{max_depth}"
                    )
                for name, value in context.items():
                    context_spec = registry.get(name)
                    if not context_spec.context:
                        raise ValueError(
                            f"deep panel uses non-context attribute {name!r}"
                        )
                    if value not in context_spec.choices:
                        raise ValueError(
                            f"deep panel value {name}={value} is not a registered bin"
                        )
                cells.append(
                    SearchCell(
                        treatment=treatment,
                        level=level,
                        comparison=str(spec.comparison_level),
                        context=context,
                        pairs=cell_pairs,
                        depth=len(context),
                        source="deep",
                    )
                )

    if not cells:
        raise ValueError(
            "generalized search has no cells: the target supports none of the "
            f"registered treatments (supported={sorted(supported)})"
        )

    unique_cells: list[SearchCell] = []
    for cell in cells:
        if cell.cell_id in seen:
            continue
        seen.add(cell.cell_id)
        unique_cells.append(cell)

    discovery_pairs = sum(cell.pairs for cell in unique_cells)
    reserve = confirmation_pairs * max_candidates
    planned = 2 * (discovery_pairs + reserve) + int(observational_applicants)
    return SearchPlan(
        cells=tuple(unique_cells),
        treatments=tuple(treatments),
        skipped_treatments=skipped,
        exhaustive_cells=exhaustive_cells,
        exhaustive_pairs=exhaustive_pairs,
        discovery_pairs=discovery_pairs,
        confirmation_reserve_pairs=reserve,
        observational_applicants=int(observational_applicants),
        planned_applicants=planned,
        probe_cap=int(probe_cap or 0),
        min_cell_size=min_cell,
        confirmation_pairs=confirmation_pairs,
        max_candidates=max_candidates,
    )


def ensure_plan_fits(plan: SearchPlan) -> None:
    """Fail loudly before any request when the plan exceeds the probe cap."""

    cap = int(plan.probe_cap)
    if cap <= 0 or plan.planned_applicants <= cap:
        return
    raise PlanTooLarge(
        "Generalized search plan exceeds the target probe cap: "
        f"{plan.planned_applicants:,} applicants planned "
        f"({plan.discovery_pairs:,} discovery pairs + "
        f"{plan.confirmation_reserve_pairs:,} confirmation-reserve pairs, "
        "both twins counted, plus "
        f"{plan.observational_applicants:,} observational applicants) "
        f"vs cap {cap:,}. The plan is not shrunk silently; reduce the panel or "
        "raise the target cap."
    )


# ---------------------------------------------------------------------- discovery
@dataclass
class CellOutcome:
    cell: SearchCell
    n: int
    b: int
    c: int
    dropped: int
    p_raw: float
    p_adjusted: float
    net_flip_rate: float
    mde: float
    observed_discordance: float
    testable: bool
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell": self.cell.cell_id,
            "treatment": self.cell.treatment,
            "level": self.cell.level,
            "context": dict(self.cell.context),
            "source": self.cell.source,
            "depth": self.cell.depth,
            "n": self.n,
            "b": self.b,
            "c": self.c,
            "dropped": self.dropped,
            "net_flip_rate": self.net_flip_rate,
            "p_raw": self.p_raw,
            "p_adjusted": self.p_adjusted,
            "mde": self.mde,
            "observed_discordance": self.observed_discordance,
            "testable": self.testable,
            "reason": self.reason,
        }


def discovery_outcomes(
    results: Sequence[CellProbeResult],
    cells: Sequence[SearchCell],
    config: dict[str, Any],
) -> list[CellOutcome]:
    """Correct every examined cell with one Holm family over testable cells."""

    if len(results) != len(cells):
        raise ValueError("results and cells must have the same length")
    search = config["audit"]["search"]
    alpha = float(config["audit"]["alpha"])
    min_cell = int(search.get("min_cell_size", config["audit"]["min_cell_size"]))
    power = float(search.get("mde_power", 0.80))
    discordance = float(search.get("mde_assumed_discordance", 0.25))

    raw = [mcnemar_exact(result.b, result.c) for result in results]
    testable_idx = [i for i, result in enumerate(results) if result.n >= min_cell]
    adjusted = [1.0] * len(results)
    if testable_idx:
        family = holm_adjust([raw[i] for i in testable_idx])
        for index, p_adj in zip(testable_idx, family):
            adjusted[index] = p_adj

    outcomes: list[CellOutcome] = []
    for cell, result, p_raw, p_adj in zip(cells, results, raw, adjusted):
        n = int(result.n)
        testable = n >= min_cell
        net = (result.b - result.c) / n if n else 0.0
        outcomes.append(
            CellOutcome(
                cell=cell,
                n=n,
                b=int(result.b),
                c=int(result.c),
                dropped=int(result.dropped),
                p_raw=p_raw,
                p_adjusted=p_adj,
                net_flip_rate=net,
                mde=minimum_detectable_effect(
                    n,
                    alpha,
                    power=power,
                    discordance=discordance,
                ),
                observed_discordance=((result.b + result.c) / n) if n else 0.0,
                testable=testable,
                reason="" if testable else f"{n} pairs < min_cell_size {min_cell}",
            )
        )
    return outcomes


def select_candidates(
    outcomes: Sequence[CellOutcome], config: dict[str, Any]
) -> tuple[list[CellOutcome], list[CellOutcome]]:
    """Rank discovery candidates and split off the ones outside the reserve."""

    search = config["audit"]["search"]
    alpha = float(config["audit"]["alpha"])
    materiality = float(config["audit"]["materiality"])
    max_candidates = int(search.get("max_confirmation_candidates", 16))
    eligible = [
        outcome
        for outcome in outcomes
        if outcome.testable
        and outcome.p_adjusted < alpha
        and outcome.net_flip_rate >= materiality
    ]
    eligible.sort(
        key=lambda outcome: (
            -outcome.net_flip_rate,
            outcome.p_raw,
            outcome.cell.cell_id,
        )
    )
    return eligible[:max_candidates], eligible[max_candidates:]


def confirmation_decision(
    result: CellProbeResult,
    outcome: CellOutcome,
    config: dict[str, Any],
    family_size: int,
) -> tuple[bool, str, float]:
    """Return ``(confirmed, reason, p_raw)`` for a fresh-twin re-test."""

    search = config["audit"]["search"]
    alpha = float(config["audit"]["alpha"])
    materiality = float(config["audit"]["materiality"])
    min_cell = int(search.get("min_cell_size", config["audit"]["min_cell_size"]))
    threshold = alpha / max(1, family_size)
    p_raw = mcnemar_exact(result.b, result.c)
    net = (result.b - result.c) / result.n if result.n else 0.0
    if result.n < min_cell:
        return False, f"confirmation n={result.n} < min_cell_size {min_cell}", p_raw
    if net <= 0 or net < materiality:
        return (
            False,
            f"confirmation net flip {net:+.4f} is below materiality "
            f"{materiality} or in the wrong direction",
            p_raw,
        )
    if p_raw >= threshold:
        return (
            False,
            f"confirmation p={p_raw:.2e} did not clear alpha/m={threshold:.2e} "
            f"(m={family_size})",
            p_raw,
        )
    if outcome.net_flip_rate <= 0:
        return False, "confirmation direction differs from discovery", p_raw
    return True, "", p_raw


def _income_bands(
    result: CellProbeResult, config: dict[str, Any]
) -> list[dict[str, Any]]:
    bands = int(config["audit"]["income_bands"])
    if not result.incomes or not result.flips:
        return []
    boundaries = income_band_boundaries(result.incomes, bands)
    rows: list[dict[str, Any]] = []
    for band_index in range(bands):
        idx = [
            i
            for i, income in enumerate(result.incomes)
            if int(np.searchsorted(boundaries, income, side="right")) == band_index
        ]
        if not idx:
            continue
        b = sum(1 for i in idx if result.flips[i] > 0)
        c = sum(1 for i in idx if result.flips[i] < 0)
        rows.append(
            {
                "band": band_index,
                "n": len(idx),
                "b": b,
                "c": c,
                "net_flip_rate": (b - c) / len(idx),
            }
        )
    return rows


def observational_context_rates(
    applicants: Sequence[Applicant],
    responses: Sequence[ModelResponse],
    registry: AttributeRegistry,
    cell: CellSpec,
) -> dict[str, float]:
    """Observed approval rates for the treatment inside the context cell."""

    target: list[bool] = []
    comparison: list[bool] = []
    for applicant, response in zip(applicants, responses):
        if any(
            registry.bin_value(name, applicant) != value
            for name, value in cell.context.items()
        ):
            continue
        value = registry.bin_value(cell.treatment, applicant)
        if value == cell.level:
            target.append(bool(response.approved))
        elif value == cell.comparison:
            comparison.append(bool(response.approved))

    def _rate(values: list[bool]) -> float:
        return sum(values) / len(values) if values else 0.0

    target_rate = _rate(target)
    comparison_rate = _rate(comparison)
    if target and comparison:
        low, high = newcombe_gap_ci(
            sum(comparison), len(comparison), sum(target), len(target)
        )
    else:
        low, high = -1.0, 1.0
    return {
        "target": target_rate,
        "comparison": comparison_rate,
        "gap": comparison_rate - target_rate,
        "target_n": float(len(target)),
        "comparison_n": float(len(comparison)),
        "gap_ci_low": low,
        "gap_ci_high": high,
    }


# -------------------------------------------------------------------- orchestration
@dataclass
class SearchResult:
    findings: list[Finding]
    summary: dict[str, Any]


def _slug(value: str) -> str:
    return (
        value.replace("|", "-")
        .replace("=", "-")
        .replace("+", "plus")
        .replace(" ", "-")
        .lower()
    )


def _event(agent: str, message: str, payload: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(agent=agent, message=message, payload=payload or {})


def _mde_table(config: dict[str, Any], sizes: Sequence[int]) -> list[dict[str, Any]]:
    search = config["audit"]["search"]
    alpha = float(config["audit"]["alpha"])
    power = float(search.get("mde_power", 0.80))
    discordance = float(search.get("mde_assumed_discordance", 0.25))
    return [
        {
            "n": int(n),
            "mde": minimum_detectable_effect(
                int(n), alpha, power=power, discordance=discordance
            ),
        }
        for n in sorted(set(int(size) for size in sizes))
    ]


def run_search(
    prober: Prober,
    model_id: int,
    plan: SearchPlan,
    config: dict[str, Any],
    seed: int,
    *,
    registry: AttributeRegistry | None = None,
    obs_applicants: Sequence[Applicant] | None = None,
    obs_responses: Sequence[ModelResponse] | None = None,
) -> Generator[AgentEvent, None, SearchResult]:
    """Run discovery and confirmation, yielding search events."""

    if registry is None:
        from auditor.registry import load_registry

        registry = load_registry(config)
    cfg = config["audit"]
    alpha = float(cfg["alpha"])
    materiality = float(cfg["materiality"])
    iterations = int(cfg["bootstrap_iterations"])
    level = float(cfg["ci_level"])
    search = cfg["search"]
    min_cell = int(search.get("min_cell_size", cfg["min_cell_size"]))
    confirmation_pairs = int(search.get("confirmation_pairs", 400))

    yield _event(
        "search",
        f"Generalized search plan: {len(plan.cells)} cells "
        f"({len(plan.treatments)} treatments), {plan.discovery_pairs:,} discovery pairs, "
        f"{plan.confirmation_reserve_pairs:,} confirmation-reserve pairs, "
        f"{plan.planned_applicants:,} applicants planned vs cap {plan.probe_cap:,}",
        {"plan": plan.summary()},
    )
    for treatment, reason in plan.skipped_treatments.items():
        yield _event(
            "search",
            f"Treatment skipped: {treatment}. {reason}",
            {"treatment": treatment, "skipped": True, "reason": reason},
        )

    discovery_seed = seed + 40_000
    confirmation_seed = seed + 60_000
    yield _event(
        "search",
        f"Phase A (discovery): {len(plan.cells)} cells on one probe set; "
        f"Holm across all examined cells",
        {"phase": "discovery", "cells": len(plan.cells), "seed": discovery_seed},
    )
    try:
        discovery_results = prober.probe_cells_sync(
            model_id, list(plan.cells), discovery_seed, "discovery"
        )
    except Exception as exc:  # noqa: BLE001
        yield _event(
            "search",
            f"Phase A aborted: {exc}",
            {"phase": "discovery", "error": str(exc)},
        )
        raise
    for event in prober.drain_events():
        yield event

    outcomes = discovery_outcomes(discovery_results, list(plan.cells), config)
    candidates, over_budget = select_candidates(outcomes, config)
    tested = [outcome for outcome in outcomes if outcome.testable]
    family_size = len(tested)
    confirmation_threshold = alpha / max(1, family_size)

    mde_table = _mde_table(
        config,
        [outcome.n for outcome in outcomes if outcome.n > 0]
        + list({cell.pairs for cell in plan.cells})
        + [confirmation_pairs],
    )
    yield _event(
        "search",
        f"Phase A complete: {len(tested)}/{len(outcomes)} cells tested, "
        f"{len(candidates)} candidates, {len(over_budget)} beyond the "
        f"confirmation reserve; Holm family m={family_size}",
        {
            "phase": "discovery",
            "cells_examined": len(outcomes),
            "cells_tested": family_size,
            "cells_not_testable": [
                outcome.cell.cell_id for outcome in outcomes if not outcome.testable
            ],
            "candidates": len(candidates),
            "candidates_over_budget": len(over_budget),
            "family_size": family_size,
            "confirmation_threshold": confirmation_threshold,
            "mde_by_cell_size": mde_table,
            "cells": [outcome.as_dict() for outcome in outcomes],
        },
    )

    findings: list[Finding] = []
    confirmed_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    not_confirmed: list[dict[str, Any]] = []
    confirmation_results: list[CellProbeResult] = []
    if candidates:
        confirmation_cells = [
            replace(outcome.cell, pairs=confirmation_pairs)
            for outcome in candidates
        ]
        yield _event(
            "search",
            f"Phase B (confirmation): {len(candidates)} candidates x "
            f"{confirmation_pairs} fresh pairs with a new seed stream",
            {
                "phase": "confirmation",
                "candidates": [outcome.cell.cell_id for outcome in candidates],
                "pairs_per_candidate": confirmation_pairs,
                "seed": confirmation_seed,
            },
        )
        try:
            confirmation_results = prober.probe_cells_sync(
                model_id, confirmation_cells, confirmation_seed, "confirmation"
            )
        except Exception as exc:  # noqa: BLE001
            yield _event(
                "search",
                f"Phase B aborted: {exc}",
                {"phase": "confirmation", "error": str(exc)},
            )
            raise
        for event in prober.drain_events():
            yield event

    family_note = f"m={family_size}"
    for rank, (outcome, result) in enumerate(
        zip(candidates, confirmation_results), start=1
    ):
        confirmed, reason, p_raw = confirmation_decision(
            result, outcome, config, family_size
        )
        p_adjusted = min(
            1.0, max(outcome.p_adjusted, p_raw * max(1, family_size))
        )
        evidence = paired_evidence(
            result.b,
            result.c,
            result.n,
            seed_key=f"confirm-{outcome.cell.cell_id}-{model_id}-{seed}",
            iterations=iterations,
            level=level,
            p_adjusted=p_adjusted,
        )
        obs = observational_context_rates(
            obs_applicants or [],
            obs_responses or [],
            registry,
            outcome.cell,
        )
        bands = _income_bands(result, config)
        finding = Finding(
            id=f"gen-{_slug(outcome.cell.cell_id)}",
            kind="generalized",
            attribute_or_subgroup=outcome.cell.label,
            target_group=outcome.cell.level,
            comparison_group=outcome.cell.comparison,
            evidence=evidence,
            observational_gap=float(obs["gap"]),
            observational_rates=obs,
            status="candidate" if confirmed else "rejected",
            reason=(
                "Confirmed on fresh twins; awaiting Skeptic review."
                if confirmed
                else f"Not confirmed on fresh twins: {reason}"
            ),
            treatment=outcome.cell.treatment,
            treatment_level=outcome.cell.level,
            context=dict(outcome.cell.context),
            search={
                "phase_a": {
                    "n": outcome.n,
                    "b": outcome.b,
                    "c": outcome.c,
                    "net_flip_rate": outcome.net_flip_rate,
                    "p_raw": outcome.p_raw,
                    "p_adjusted": outcome.p_adjusted,
                    "mde": outcome.mde,
                    "observed_discordance": outcome.observed_discordance,
                },
                "phase_b": {
                    "n": result.n,
                    "b": result.b,
                    "c": result.c,
                    "net_flip_rate": (
                        (result.b - result.c) / result.n if result.n else 0.0
                    ),
                    "p_raw": p_raw,
                    "threshold": confirmation_threshold,
                },
                "confirmed": confirmed,
                "rank": rank,
                "cell": outcome.cell.cell_id,
                "depth": outcome.cell.depth,
                "source": outcome.cell.source,
                "family_size": family_size,
                "confirmation_threshold": confirmation_threshold,
                "confirmation_seed": confirmation_seed,
                "discovery_seed": discovery_seed,
                "income_bands": bands,
            },
        )
        findings.append(finding)
        row = {
            "cell": outcome.cell.cell_id,
            "rank": rank,
            "confirmed": confirmed,
            "reason": reason,
            "discovery": finding.search["phase_a"],
            "confirmation": finding.search["phase_b"],
        }
        candidate_rows.append(
            {
                "cell": outcome.cell.cell_id,
                "rank": rank,
                "discovery_net_flip_rate": outcome.net_flip_rate,
                "discovery_p_adjusted": outcome.p_adjusted,
                "mde": outcome.mde,
                "confirmed": confirmed,
            }
        )
        if confirmed:
            confirmed_rows.append(row)
            yield _event(
                "search",
                f"Confirmed {outcome.cell.label}: fresh-twin net "
                f"{finding.search['phase_b']['net_flip_rate']:+.4f}, "
                f"p={p_raw:.2e} < {confirmation_threshold:.2e} ({family_note})",
                row,
            )
        else:
            not_confirmed.append(row)
            yield _event(
                "search",
                f"Not confirmed {outcome.cell.label}: {reason}",
                row,
            )

    for outcome in over_budget:
        evidence = paired_evidence(
            outcome.b,
            outcome.c,
            outcome.n,
            seed_key=f"discover-{outcome.cell.cell_id}-{model_id}-{seed}",
            iterations=iterations,
            level=level,
            p_adjusted=outcome.p_adjusted,
        )
        obs = observational_context_rates(
            obs_applicants or [],
            obs_responses or [],
            registry,
            outcome.cell,
        )
        findings.append(
            Finding(
                id=f"gen-{_slug(outcome.cell.cell_id)}",
                kind="generalized",
                attribute_or_subgroup=outcome.cell.label,
                target_group=outcome.cell.level,
                comparison_group=outcome.cell.comparison,
                evidence=evidence,
                observational_gap=float(obs["gap"]),
                observational_rates=obs,
                status="rejected",
                reason=(
                    "candidate_not_confirmed_budget: the discovery candidate "
                    f"ranked outside the {plan.max_candidates}-candidate "
                    "confirmation reserve and was not re-tested."
                ),
                treatment=outcome.cell.treatment,
                treatment_level=outcome.cell.level,
                context=dict(outcome.cell.context),
                search={
                    "phase_a": {
                        "n": outcome.n,
                        "b": outcome.b,
                        "c": outcome.c,
                        "net_flip_rate": outcome.net_flip_rate,
                        "p_raw": outcome.p_raw,
                        "p_adjusted": outcome.p_adjusted,
                        "mde": outcome.mde,
                        "observed_discordance": outcome.observed_discordance,
                    },
                    "phase_b": None,
                    "confirmed": False,
                    "rank": None,
                    "cell": outcome.cell.cell_id,
                    "depth": outcome.cell.depth,
                    "source": outcome.cell.source,
                    "family_size": family_size,
                    "confirmation_threshold": confirmation_threshold,
                    "income_bands": [],
                },
            )
        )
        row = {
            "cell": outcome.cell.cell_id,
            "rank": None,
            "confirmed": False,
            "reason": "candidate_not_confirmed_budget",
        }
        not_confirmed.append(row)
        yield _event(
            "search",
            f"Candidate not confirmed (budget): {outcome.cell.label}",
            row,
        )

    confirmed_count = len(confirmed_rows)
    yield _event(
        "search",
        f"Phase B complete: {confirmed_count}/{len(candidates)} candidates confirmed; "
        f"{confirmed_count} confirmed cell(s) become findings",
        {
            "phase": "confirmation",
            "candidates": len(candidates),
            "confirmed": confirmed_count,
            "not_confirmed": not_confirmed,
            "mde_by_cell_size": mde_table,
        },
    )

    summary = {
        "plan": plan.summary(),
        "discovery_seed": discovery_seed,
        "confirmation_seed": confirmation_seed,
        "cells_examined": len(outcomes),
        "cells_tested": family_size,
        "cells_not_testable": [
            outcome.cell.cell_id for outcome in outcomes if not outcome.testable
        ],
        "phase_a_pairs": sum(outcome.n for outcome in outcomes),
        "phase_b_pairs": sum(result.n for result in confirmation_results),
        "discovery_results": [outcome.as_dict() for outcome in outcomes],
        "candidates": candidate_rows,
        "confirmed": confirmed_rows,
        "not_confirmed": not_confirmed,
        "confirmation_threshold": confirmation_threshold,
        "mde_by_cell_size": mde_table,
        "materiality": materiality,
        "alpha": alpha,
    }
    return SearchResult(findings=findings, summary=summary)
