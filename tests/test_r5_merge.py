"""Hand-built tests for R5 Step 4: Skeptic redundancy and finding merge."""

from __future__ import annotations

import copy

from auditor.pipeline import collect_audit
from auditor.skeptic import merge_redundant
from config_loader import load_config
from schemas import Evidence, Finding, ModelResponse
from targets.base import TargetAdapter


def _evidence(net: float, n: int = 400) -> Evidence:
    b = int(round((net + 1) * n / 2))
    c = n - b
    return Evidence(
        n=n,
        b=b,
        c=c,
        net_flip_rate=net,
        ci_low=net,
        ci_high=net,
        p_raw=0.0001,
        p_adjusted=0.001,
    )


def _finding(
    identifier: str,
    treatment: str,
    level: str,
    context: dict[str, str],
    net: float,
    status: str = "kept",
) -> Finding:
    return Finding(
        id=identifier,
        kind="generalized",
        attribute_or_subgroup=f"{treatment}={level} in {context or 'main'}",
        target_group=level,
        comparison_group="baseline",
        evidence=_evidence(net),
        observational_gap=0.0,
        status=status,  # type: ignore[arg-type]
        reason="hand-built",
        treatment=treatment,
        treatment_level=level,
        context=dict(context),
        search={},
    )


def _config() -> dict:
    return copy.deepcopy(load_config())


def test_symmetric_orientations_merge_into_one_primary():
    left = _finding(
        "gen-pincode", "pincode_group", "P2", {"gender": "female"}, 0.30
    )
    right = _finding(
        "gen-gender", "gender", "female", {"pincode_group": "P2"}, 0.31
    )
    findings = [left, right]

    merges = merge_redundant(findings, _config())

    kept = [finding for finding in findings if finding.status == "kept"]
    merged = [finding for finding in findings if finding.status == "merged"]
    assert len(kept) == 1
    assert len(merged) == 1
    assert merged[0].merged_into == kept[0].id
    assert kept[0].search["merged_cells"] == [merged[0].id]
    assert kept[0].search["redundancy"]["passed"] is True
    assert merged[0].search["redundancy"]["passed"] is False
    assert merged[0].search["redundancy"]["primary"] == kept[0].id
    assert "Merged into primary finding" in merged[0].reason
    assert any(entry["merged"] is not None for entry in merges)


def test_materially_stronger_specific_cell_becomes_primary():
    broad = _finding("gen-age-main", "age", "45+", {}, 0.10)
    exact = _finding(
        "gen-age-deep",
        "age",
        "45+",
        {"gender": "female", "urban_rural": "rural", "name_group": "N2"},
        0.35,
    )
    findings = [broad, exact]

    merge_redundant(findings, _config())

    assert exact.status == "kept"
    assert broad.status == "merged"
    assert broad.merged_into == exact.id
    assert exact.search["merged_cells"] == [broad.id]


def test_context_without_a_material_gain_merges_into_the_main_effect():
    main = _finding("gen-age-main", "age", "45+", {}, 0.20)
    context = _finding(
        "gen-age-credit", "age", "45+", {"credit_score": "mid"}, 0.21
    )
    findings = [main, context]

    merge_redundant(findings, _config())

    assert main.status == "kept"
    assert context.status == "merged"
    assert context.merged_into == main.id


def test_incomparable_main_effects_are_not_merged():
    pincode = _finding("gen-pincode", "pincode_group", "P2", {}, 0.10)
    gender = _finding("gen-gender", "gender", "female", {}, 0.12)
    findings = [pincode, gender]

    merge_redundant(findings, _config())

    assert pincode.status == "kept"
    assert gender.status == "kept"
    assert pincode.merged_into is None
    assert gender.merged_into is None


def test_different_levels_of_the_same_attribute_are_not_merged():
    younger = _finding("gen-age-35", "age", "35-44", {}, 0.06)
    older = _finding("gen-age-45", "age", "45+", {}, 0.12)
    findings = [younger, older]

    merge_redundant(findings, _config())

    assert younger.status == "kept"
    assert older.status == "kept"


def test_rejected_and_immaterial_findings_are_left_alone():
    kept = _finding("gen-kept", "age", "45+", {}, 0.20)
    rejected = _finding(
        "gen-rejected", "age", "45+", {"credit_score": "mid"}, 0.21, "rejected"
    )
    immaterial = _finding(
        "gen-immaterial",
        "age",
        "45+",
        {"loan_amount": "high"},
        0.22,
        "immaterial",
    )
    findings = [kept, rejected, immaterial]

    merge_redundant(findings, _config())

    assert kept.status == "kept"
    assert rejected.status == "rejected"
    assert immaterial.status == "immaterial"
    assert rejected.merged_into is None
    assert immaterial.merged_into is None


class _NestedTarget(TargetAdapter):
    """Penalises female applicants only in the 45+ x rural x N2 cell."""

    name = "nested-target"
    probe_cap = 100_000
    supports_mitigation = False
    supported_probes = frozenset({"gender"})
    supported_treatments = frozenset({"gender"})

    def __init__(self) -> None:
        self._used = 0

    @property
    def probes_used(self) -> int:
        return self._used

    def reset(self) -> None:
        self._used = 0

    async def health(self) -> dict:
        return {"status": "ok"}

    async def score_batch(self, applicants):
        self._used += len(applicants)
        responses = []
        for applicant in applicants:
            penalised = (
                applicant.gender == "female"
                and applicant.age_band == "45+"
                and applicant.urban_rural == "rural"
                and applicant.name_group == "N2"
            )
            approved = applicant.credit_score >= 650 and not penalised
            responses.append(
                ModelResponse(approved=approved, score=700.0 if approved else 400.0)
            )
        return responses


def test_end_to_end_confirmed_cells_collapse_to_one_kept_finding():
    config = copy.deepcopy(load_config())
    config["audit"]["search"]["enabled"] = True
    config["audit"]["search"]["deep_panel"] = {
        "gender": [{"age": "45+", "urban_rural": "rural", "name_group": "N2"}]
    }
    _, report = collect_audit(
        12,
        "http://nested.test",
        config,
        seed=19,
        target=_NestedTarget(),
        include_mitigation=False,
        include_narrative=False,
    )
    kept = [finding for finding in report.findings if finding.status == "kept"]
    merged = [finding for finding in report.findings if finding.status == "merged"]
    assert len(kept) == 1
    assert merged, "the overlapping confirmed cells should stay visible as merged"
    assert all(finding.merged_into == kept[0].id for finding in merged)
    search = report.observational["search"]
    assert search["kept_after_merge"] == [kept[0].id]
    assert search["merged"]
