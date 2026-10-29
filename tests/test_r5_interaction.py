"""Tests for the R5 interaction search (Step 3)."""

from __future__ import annotations

import copy

import pytest

from auditor.interaction import (
    PlanTooLarge,
    SearchCell,
    build_search_plan,
    confirmation_decision,
    discovery_outcomes,
    ensure_plan_fits,
    select_candidates,
)
from auditor.prober import CellProbeResult, Prober
from auditor.registry import load_registry, minimum_detectable_effect
from auditor.statistician import holm_adjust
from auditor.pipeline import collect_audit
from config_loader import load_config
from schemas import ModelResponse
from targets.base import TargetAdapter


@pytest.fixture(scope="module")
def config() -> dict:
    return load_config()


@pytest.fixture(scope="module")
def registry(config):
    return load_registry(config)


def _cell(treatment="gender", level="female", comparison="male", context=None):
    return SearchCell(
        treatment=treatment,
        level=level,
        comparison=comparison,
        context=context or {},
        pairs=200,
        depth=len(context or {}),
        source="deep" if context else "main",
    )


def _result(cell: SearchCell, n=200, b=80, c=10) -> CellProbeResult:
    return CellProbeResult(
        treatment=cell.treatment,
        level=cell.level,
        comparison=cell.comparison,
        context=dict(cell.context),
        phase="discovery",
        n=n,
        b=b,
        c=c,
        seed=1,
        incomes=[600_000.0] * n,
        flips=[1] * b + [-1] * c + [0] * max(0, n - b - c),
    )


# ------------------------------------------------------------------------ plan
def test_plan_matches_the_pre_registered_panel(config, registry):
    plan = build_search_plan(config, registry, probe_cap=100_000)
    assert len(plan.cells) == 110
    by_source = {source: 0 for source in ("main", "depth1", "deep")}
    for cell in plan.cells:
        by_source[cell.source] += 1
    assert by_source == {"main": 5, "depth1": 89, "deep": 16}
    assert plan.discovery_pairs == 26_000
    assert plan.confirmation_reserve_pairs == 6_400
    assert plan.planned_applicants == 68_800
    assert plan.exhaustive_cells == 7_122
    assert plan.exhaustive_pairs > plan.discovery_pairs


def test_every_planned_cell_is_registered_and_excludes_its_treatment(config, registry):
    plan = build_search_plan(config, registry)
    for cell in plan.cells:
        spec = registry.get(cell.treatment)
        assert cell.treatment in registry.treatment_attributes()
        assert cell.comparison == spec.comparison_level
        assert cell.treatment not in cell.context
        for name, value in cell.context.items():
            assert registry.get(name).context is True
            assert value in registry.get(name).choices


def test_age_gets_full_panel_only_at_the_highest_level(config, registry):
    plan = build_search_plan(config, registry)
    age_cells = [cell for cell in plan.cells if cell.treatment == "age"]
    lower = [cell for cell in age_cells if cell.level == "35-44"]
    higher = [cell for cell in age_cells if cell.level == "45+"]
    assert len(lower) == 1 and lower[0].source == "main"
    assert any(cell.source == "depth1" for cell in higher)
    assert any(cell.source == "deep" for cell in higher)


def test_unsupported_treatments_are_skipped_with_a_reason(config, registry):
    plan = build_search_plan(
        config, registry, supported_treatments={"gender"}, probe_cap=100_000
    )
    assert plan.treatments == ("gender",)
    assert set(plan.skipped_treatments) == {"age", "pincode_group", "name_group"}
    assert all(
        "does not support" in reason
        for reason in plan.skipped_treatments.values()
    )
    assert all(cell.treatment == "gender" for cell in plan.cells)


def test_plan_fits_under_the_cap(config, registry):
    plan = build_search_plan(config, registry, probe_cap=100_000)
    ensure_plan_fits(plan)


def test_plan_fails_loudly_above_the_cap(config, registry):
    plan = build_search_plan(config, registry, probe_cap=10_000)
    with pytest.raises(PlanTooLarge) as excinfo:
        ensure_plan_fits(plan)
    message = str(excinfo.value)
    assert "68,800" in message
    assert "10,000" in message
    assert "not shrunk silently" in message


# ------------------------------------------------------------------ discovery
def test_holm_family_covers_all_testable_cells_only():
    cells = [
        _cell(context={"age": "45+"}),
        _cell(context={"age": "<35"}),
        _cell(context={"name_group": "N2"}),
    ]
    results = [
        _result(cells[0], n=200, b=80, c=10),
        _result(cells[1], n=200, b=40, c=30),
        _result(cells[2], n=150, b=100, c=0),  # below min_cell_size
    ]
    outcomes = discovery_outcomes(results, cells, load_config())
    assert [outcome.testable for outcome in outcomes] == [True, True, False]
    assert "min_cell_size" in outcomes[2].reason
    expected = holm_adjust([outcomes[0].p_raw, outcomes[1].p_raw])
    assert outcomes[0].p_adjusted == pytest.approx(expected[0])
    assert outcomes[1].p_adjusted == pytest.approx(expected[1])
    assert outcomes[2].p_adjusted == 1.0


def test_mde_is_reported_from_the_cell_size():
    cell = _cell()
    outcome = discovery_outcomes([_result(cell, n=200)], [cell], load_config())[0]
    assert outcome.mde == pytest.approx(minimum_detectable_effect(200, 0.05))
    assert outcome.observed_discordance == pytest.approx(90 / 200)
    small = discovery_outcomes([_result(cell, n=2000)], [cell], load_config())[0]
    assert small.mde < outcome.mde


def test_candidates_are_ranked_and_cut_at_the_reserve():
    config = load_config()
    cells = [_cell(context={"name_group": f"N{i % 3 + 1}"}) for i in range(18)]
    results = [
        _result(cell, n=200, b=80 + index * 5, c=10) for index, cell in enumerate(cells)
    ]
    outcomes = discovery_outcomes(results, cells, config)
    candidates, over_budget = select_candidates(outcomes, config)
    assert len(candidates) == 16
    assert len(over_budget) == 2
    nets = [outcome.net_flip_rate for outcome in candidates]
    assert nets == sorted(nets, reverse=True)


def test_confirmation_requires_the_conservative_threshold():
    config = load_config()
    cell = _cell(context={"age": "45+"})
    outcome = discovery_outcomes([_result(cell, n=200)], [cell], config)[0]
    strong = _result(cell, n=400, b=140, c=10)
    confirmed, reason, _p = confirmation_decision(strong, outcome, config, 110)
    assert confirmed and reason == ""

    weak = _result(cell, n=400, b=48, c=42)
    confirmed, reason, _p = confirmation_decision(weak, outcome, config, 110)
    assert not confirmed
    assert "below materiality" in reason or "did not clear" in reason


# ------------------------------------------------------------------ end to end
class RuleTarget(TargetAdapter):
    """A tiny black box with a planted gender x age x rural x name rule."""

    name = "rule-target"
    probe_cap = 100_000
    supported_probes = frozenset({"gender"})
    supported_treatments = frozenset({"gender"})
    supports_mitigation = False

    def __init__(self) -> None:
        self._used = 0
        self.seen: list[str] = []

    @property
    def probes_used(self) -> int:
        return self._used

    def reset(self) -> None:
        self._used = 0

    async def health(self) -> dict:
        return {"status": "ok"}

    async def score_batch(self, applicants):
        self._used += len(applicants)
        self.seen.extend(applicant.id for applicant in applicants)
        rows = []
        for applicant in applicants:
            penalised = (
                applicant.gender == "female"
                and applicant.age_band == "45+"
                and applicant.urban_rural == "rural"
                and applicant.name_group == "N2"
            )
            approved = applicant.credit_score >= 650 and not penalised
            rows.append(
                ModelResponse(approved=approved, score=700.0 if approved else 400.0)
            )
        return rows


def _rule_config() -> dict:
    config = copy.deepcopy(load_config())
    config["audit"]["search"]["enabled"] = True
    config["audit"]["search"]["deep_panel"] = {
        "gender": [{"age": "45+", "urban_rural": "rural", "name_group": "N2"}]
    }
    return config


def test_generalized_audit_finds_the_deep_cell_and_confirms_it_on_fresh_twins():
    config = _rule_config()
    target = RuleTarget()
    events, report = collect_audit(
        2,
        "http://rule-target.test",
        config,
        seed=7,
        target=target,
        include_mitigation=False,
        include_narrative=False,
    )
    kept = [finding for finding in report.findings if finding.status == "kept"]
    assert len(kept) == 1
    finding = kept[0]
    assert finding.kind == "generalized"
    assert finding.treatment == "gender"
    assert finding.treatment_level == "female"
    assert finding.context == {
        "age": "45+",
        "urban_rural": "rural",
        "name_group": "N2",
    }
    assert finding.search["confirmed"] is True
    assert finding.search["phase_a"]["n"] == 200
    assert finding.search["phase_b"]["n"] == 400
    assert finding.search["phase_b"]["n"] == config["audit"]["search"]["confirmation_pairs"]

    search = report.observational["search"]
    assert search["cells_examined"] == 25
    assert search["cells_tested"] == 25
    assert search["candidates"][0]["cell"].startswith("gender|female")
    assert search["confirmed"][0]["confirmed"] is True
    assert {row["n"] for row in search["mde_by_cell_size"]} >= {200, 400}

    # Both phases emit agent events, and the plan is shown before any probe.
    agents = [event.agent for event in events]
    assert agents.count("search") >= 6
    discovery_events = [
        event
        for event in events
        if event.agent == "search" and event.payload.get("phase") == "discovery"
    ]
    confirmation_events = [
        event
        for event in events
        if event.agent == "search" and event.payload.get("phase") == "confirmation"
    ]
    assert discovery_events and confirmation_events
    assert any(
        event.payload.get("plan", {}).get("planned_applicants") == 28_400
        for event in events
    )


def test_clean_control_produces_no_candidates_and_no_findings():
    class CleanTarget(RuleTarget):
        async def score_batch(self, applicants):
            self._used += len(applicants)
            self.seen.extend(applicant.id for applicant in applicants)
            return [
                ModelResponse(
                    approved=applicant.credit_score >= 650,
                    score=700.0 if applicant.credit_score >= 650 else 400.0,
                )
                for applicant in applicants
            ]

    config = _rule_config()
    _, report = collect_audit(
        15,
        "http://clean.test",
        config,
        seed=11,
        target=CleanTarget(),
        include_mitigation=False,
        include_narrative=False,
    )
    assert report.findings == []
    assert report.observational["search"]["candidates"] == []
    assert report.observational["search"]["confirmed"] == []


def test_probe_cells_uses_a_fresh_seed_stream_for_confirmation():
    config = load_config()
    target = RuleTarget()
    prober = Prober("http://rule-target.test", config, target=target)
    cell = SearchCell(
        treatment="gender",
        level="female",
        comparison="male",
        context={},
        pairs=20,
        depth=0,
        source="main",
    )
    prober.probe_cells_sync(2, [cell], 111, "discovery")
    discovery_ids = set(target.seen)
    target.seen.clear()
    prober.probe_cells_sync(2, [cell], 222, "confirmation")
    confirmation_ids = set(target.seen)
    assert discovery_ids
    assert confirmation_ids
    assert discovery_ids.isdisjoint(confirmation_ids)
