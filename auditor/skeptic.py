"""Rule-based Skeptic.

No LLM is used here. The Skeptic receives one candidate finding plus an optional
income-matched re-test and records every check, including failures. Rejected
candidates stay in the report.

Checks
------
1. min_sample_size: at least min_pairs (single) or min_cell_size (intersectional).
2. significance_after_correction: Holm-adjusted p < alpha.
3. materiality: net flip rate >= pre-registered materiality, in the harm direction.
4. symmetric_noise: b > c and directional asymmetry (b-c)/(b+c) >= 0.20.
5. income_matched_persistence: re-test inside income quintiles remains significant
   and material. This distinguishes a signal effect from an income explanation.
6. confounding_check: fails only when an observational gap >= materiality exists
   together with a counterfactual net flip < materiality. That is the signature
   of a gap explained by legitimate factors.
7. redundancy (R5 generalized findings): overlapping confirmed cells are merged
   into one primary finding. A cell is redundant when its described subgroup is
   nested inside another kept cell's subgroup and is not materially stronger, or
   when it is a sibling context under the same treatment whose confirmation net
   flips are statistically indistinguishable (R5.1). Sibling clusters collapse to
   the shared treatment and the narrowest common context. Merged cells stay in the
   report with ``status="merged"`` and a reason.

Status precedence: a significant but sub-materiality effect is "immaterial",
never "kept". A directional zero-effect candidate is "rejected".
"""

from __future__ import annotations

import math
from typing import Any

from schemas import Check, Evidence, Finding, SkepticVerdict


def review(
    finding: Finding,
    config: dict[str, Any],
    matched_evidence: Evidence | None = None,
    matched_bands: list[dict[str, Any]] | None = None,
) -> SkepticVerdict:
    cfg = config["audit"]
    alpha = float(cfg["alpha"])
    materiality = float(cfg["materiality"])
    min_pairs = int(cfg["min_pairs"])
    min_cell = int(cfg["min_cell_size"])
    ev = finding.evidence
    checks: list[Check] = []

    required_n = (
        min_cell
        if finding.kind in {"intersectional", "generalized"}
        else min_pairs
    )
    min_ok = ev.n >= required_n
    checks.append(
        Check(
            name="min_sample_size",
            passed=min_ok,
            detail=f"n={ev.n}; required {required_n} for {finding.kind}",
        )
    )

    sig_ok = ev.p_adjusted < alpha
    sig_detail = (
        f"corrected p={ev.p_adjusted:.2e}; alpha={alpha}"
        if finding.kind == "generalized"
        else f"Holm-adjusted p={ev.p_adjusted:.2e}; alpha={alpha}"
    )
    checks.append(
        Check(
            name="significance_after_correction",
            passed=sig_ok,
            detail=sig_detail,
        )
    )

    material_ok = ev.net_flip_rate >= materiality
    checks.append(
        Check(
            name="materiality",
            passed=material_ok,
            detail=(
                f"net flip rate={ev.net_flip_rate:+.4f}; materiality threshold={materiality}"
            ),
        )
    )

    discordant = ev.b + ev.c
    asymmetry = (ev.b - ev.c) / discordant if discordant else 0.0
    directional_ok = bool(ev.b > ev.c and asymmetry >= 0.20)
    checks.append(
        Check(
            name="symmetric_noise",
            passed=directional_ok,
            detail=(
                f"b={ev.b}, c={ev.c}, asymmetry={asymmetry:+.2f}; "
                "needs b>c and asymmetry>=0.20 (guards against random b≈c flips)"
            ),
        )
    )

    if matched_evidence is None:
        matched_ok = False
        matched_detail = "not run: prerequisite checks failed or no re-test available"
    else:
        matched_required = (
            required_n if finding.kind == "generalized" else min_pairs
        )
        matched_ok = bool(
            matched_evidence.n >= matched_required
            and matched_evidence.p_raw < alpha
            and matched_evidence.net_flip_rate >= materiality
        )
        band_text = ""
        if matched_bands:
            positives = sum(1 for b in matched_bands if b["net_flip_rate"] > 0)
            band_text = (
                f"; {positives}/{len(matched_bands)} income bands positive, "
                f"bands={[(b['band'], round(b['net_flip_rate'], 3)) for b in matched_bands]}"
            )
        if finding.kind == "generalized":
            matched_detail = (
                "confirmation twins hold every legitimate signal fixed "
                f"(n={matched_evidence.n}, net={matched_evidence.net_flip_rate:+.4f}, "
                f"p={matched_evidence.p_raw:.2e}){band_text}"
            )
        else:
            matched_detail = (
                f"n={matched_evidence.n}, net={matched_evidence.net_flip_rate:+.4f}, "
                f"p={matched_evidence.p_raw:.2e}{band_text}"
            )
    checks.append(
        Check(
            name="income_matched_persistence",
            passed=matched_ok,
            detail=matched_detail,
        )
    )

    gap_material = finding.observational_gap >= materiality
    counterfactual_zero = ev.net_flip_rate < materiality
    confound_ok = not (gap_material and counterfactual_zero)
    if confound_ok:
        confound_detail = (
            f"observational gap={finding.observational_gap:+.4f}, "
            f"net flip={ev.net_flip_rate:+.4f}: no confounded-gap signature"
        )
    else:
        confound_detail = (
            f"observational gap={finding.observational_gap:+.4f} but "
            f"net flip={ev.net_flip_rate:+.4f}: gap is consistent with legitimate "
            "factors (e.g. income) rather than a signal-specific penalty"
        )
    checks.append(
        Check(name="confounding_check", passed=confound_ok, detail=confound_detail)
    )

    if not min_ok:
        status, reason = "rejected", (
            f"Rejected: sample too small (n={ev.n} < {required_n})."
        )
    elif not sig_ok:
        if not confound_ok:
            status, reason = "rejected", (
                "Rejected as confounded: the observational gap "
                f"({finding.observational_gap:+.4f}) is not accompanied by a "
                f"material counterfactual effect (net flip {ev.net_flip_rate:+.4f}). "
                "This is consistent with legitimate factors such as income."
            )
        else:
            status, reason = "rejected", (
                f"Rejected: not significant after Holm correction "
                f"(p_adj={ev.p_adjusted:.2e})."
            )
    elif not material_ok:
        if ev.net_flip_rate > 0:
            status, reason = "immaterial", (
                f"Significant but immaterial: net flip rate {ev.net_flip_rate:+.4f} "
                f"is below the pre-registered materiality threshold {materiality}."
            )
        else:
            status, reason = "rejected", (
                f"Rejected: counterfactual effect is in the opposite direction "
                f"(net flip {ev.net_flip_rate:+.4f})."
            )
    elif not directional_ok:
        status, reason = "rejected", (
            "Rejected: no stable directional effect (b is not materially larger than c)."
        )
    elif not matched_ok:
        if finding.kind == "generalized":
            status, reason = "rejected", (
                "Rejected: the fresh confirmation sample did not meet the "
                "held-fixed sample/significance requirement."
            )
        else:
            status, reason = "rejected", (
                "Rejected: the effect did not persist in the income-matched re-test."
            )
    else:
        if finding.kind == "generalized":
            context = ", ".join(
                f"{key}={value}" for key, value in finding.context.items()
            ) or "main effect"
            status, reason = "kept", (
                f"Kept: treatment {finding.treatment}={finding.treatment_level} in "
                f"context {context}; {ev.n} fresh confirmation pairs, net flip "
                f"{ev.net_flip_rate:+.4f} (95% CI {ev.ci_low:+.4f} to "
                f"{ev.ci_high:+.4f}), corrected p={ev.p_adjusted:.2e}; twins hold "
                "every legitimate signal fixed."
            )
        else:
            status, reason = "kept", (
                f"Kept: {ev.n} pairs, net flip {ev.net_flip_rate:+.4f} "
                f"(95% CI {ev.ci_low:+.4f} to {ev.ci_high:+.4f}), "
                f"Holm-adjusted p={ev.p_adjusted:.2e}; effect persists in the "
                "income-matched re-test."
            )

    return SkepticVerdict(
        finding_id=finding.id,
        checks=checks,
        final_status=status,  # type: ignore[arg-type]
        reason=reason,
    )


# --------------------------------------------------------------------- redundancy
def _subgroup(finding: Finding) -> dict[str, str]:
    """The subgroup a generalized finding actually describes.

    The treatment level is part of the subgroup, and the context adds the
    conditions. Two findings with the same set of ``attribute=value`` pairs are
    the symmetric description of one cell (e.g. pincode P2 in ``gender=female``
    and gender female in ``pincode_group=P2``).
    """

    if finding.kind != "generalized" or not finding.treatment:
        return {}
    subgroup = {finding.treatment: finding.treatment_level or ""}
    subgroup.update(finding.context)
    return subgroup


def _is_subset(left: dict[str, str], right: dict[str, str]) -> bool:
    return all(right.get(key) == value for key, value in left.items())


def _sibling_p_value(left: Finding, right: Finding) -> float:
    """Two-sided z-test for a difference in confirmation net flip rates.

    Var((b - c) / n) is (b + c) / n^2 under the discordant-count approximation,
    which is the same variance the confidence interval uses. This is the exact
    test frozen in ``expected_findings.md`` under R5.1.
    """

    def variance(finding: Finding) -> float:
        evidence = finding.evidence
        return (evidence.b + evidence.c) / (evidence.n**2) if evidence.n else 0.0

    net_left = left.evidence.net_flip_rate
    net_right = right.evidence.net_flip_rate
    scale = math.sqrt(variance(left) + variance(right))
    if scale == 0:
        return 1.0 if net_left == net_right else 0.0
    z_value = (net_left - net_right) / scale
    return math.erfc(abs(z_value) / math.sqrt(2.0))


def _are_siblings(left: Finding, right: Finding, alpha: float) -> bool:
    """Same treatment and level, non-nested contexts, indistinguishable nets."""

    if (
        left.treatment != right.treatment
        or left.treatment_level != right.treatment_level
    ):
        return False
    left_group = _subgroup(left)
    right_group = _subgroup(right)
    if _is_subset(left_group, right_group) or _is_subset(right_group, left_group):
        return False
    return _sibling_p_value(left, right) >= alpha


def _common_context(members: list[Finding]) -> dict[str, str]:
    """The narrowest common context: keys every member pins to the same value."""

    common = dict(members[0].context or {})
    for member in members[1:]:
        context = member.context or {}
        common = {
            key: value
            for key, value in common.items()
            if context.get(key) == value
        }
    return common


def _describe(primary: Finding, common: dict[str, str]) -> str:
    base = f"{primary.treatment}={primary.treatment_level} vs {primary.comparison_group}"
    if not common:
        return f"{base} (main effect)"
    context = ", ".join(f"{key}={value}" for key, value in common.items())
    return f"{base} in {context}"


def _select_primary(
    members: list[Finding], materiality: float
) -> Finding:
    """Pick the best description of one overlapping cluster of kept cells.

    The most general cell is the parsimonious primary unless a more specific
    cell is materially stronger. That second condition is what makes a
    concentrated interaction (e.g. all four attributes) displace the diluted
    broader cell, while a broad effect with no materially stronger context stays
    a main effect.
    """

    def size(finding: Finding) -> int:
        return len(_subgroup(finding))

    general = min(members, key=lambda f: (size(f), -f.evidence.n, f.id))
    strongest = max(
        members, key=lambda f: (f.evidence.net_flip_rate, size(f), f.id)
    )
    if strongest.evidence.net_flip_rate - general.evidence.net_flip_rate >= materiality:
        return strongest
    return general


def merge_redundant(
    findings: list[Finding], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Merge overlapping or indistinguishable kept generalized cells.

    Two links form a cluster. A cell is nested when its described subgroup is
    contained in another kept cell's subgroup. Two cells are siblings when they
    share the treatment and level, neither subgroup contains the other, and their
    confirmation net flips are statistically indistinguishable (R5.1). Clusters
    are re-formed after each merge so a re-described main effect can absorb a
    separate deep cell in a later pass.

    Only ``status == "kept"`` generalized findings participate. Rejected,
    immaterial, and already-merged findings are untouched. Every merge is
    returned and also recorded on the findings so the report keeps both the
    primary and the merged cells visible with reasons.
    """

    materiality = float(config["audit"]["materiality"])
    alpha = float(config["audit"]["alpha"])
    merges: list[dict[str, Any]] = []

    def cluster(kept: list[Finding]) -> list[list[Finding]]:
        parent = {finding.id: finding.id for finding in kept}

        def find(identifier: str) -> str:
            while parent[identifier] != identifier:
                parent[identifier] = parent[parent[identifier]]
                identifier = parent[identifier]
            return identifier

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for index, left in enumerate(kept):
            left_group = _subgroup(left)
            for right in kept[index + 1 :]:
                right_group = _subgroup(right)
                nested = _is_subset(left_group, right_group) or _is_subset(
                    right_group, left_group
                )
                if nested or _are_siblings(left, right, alpha):
                    union(left.id, right.id)

        groups: dict[str, list[Finding]] = {}
        for finding in kept:
            groups.setdefault(find(finding.id), []).append(finding)
        return list(groups.values())

    for finding in findings:
        if finding.kind == "generalized" and finding.status == "kept":
            finding.search.setdefault("redundancy", {"passed": True, "primary": None})

    while True:
        kept = [
            finding
            for finding in findings
            if finding.kind == "generalized" and finding.status == "kept"
        ]
        groups = [members for members in cluster(kept) if len(members) >= 2]
        if not groups:
            break

        for members in groups:
            primary = _select_primary(members, materiality)
            general = min(
                members, key=lambda f: (len(_subgroup(f)), -f.evidence.n, f.id)
            )
            same_treatment = (
                len({(member.treatment, member.treatment_level) for member in members})
                == 1
            )
            sibling_cluster = same_treatment and any(
                _are_siblings(left, right, alpha)
                for index, left in enumerate(members)
                for right in members[index + 1 :]
            )
            primary_group_before = {
                member.id: _subgroup(member) for member in members
            }
            merged = [member for member in members if member.id != primary.id]
            merged.sort(key=lambda f: (len(_subgroup(f)), f.id))

            materially_stronger = (
                primary.evidence.net_flip_rate
                - general.evidence.net_flip_rate
                >= materiality
            )
            common: dict[str, str] = dict(primary.context or {})
            re_described = False
            if sibling_cluster and not materially_stronger:
                common = _common_context(members)
                if common != dict(primary.context or {}):
                    primary.context = dict(common)
                    primary.attribute_or_subgroup = _describe(primary, common)
                    re_described = True

            for member in merged:
                member_group = primary_group_before[member.id]
                primary_group = primary_group_before[primary.id]
                nested = _is_subset(member_group, primary_group) or _is_subset(
                    primary_group, member_group
                )
                member.status = "merged"  # type: ignore[assignment]
                member.merged_into = primary.id
                p_value = None if nested else _sibling_p_value(member, primary)
                if nested:
                    detail = (
                        f"subgroup {member_group} overlaps primary {primary.id} "
                        f"({primary.attribute_or_subgroup}) and is not materially "
                        "stronger"
                    )
                    reason = (
                        f"Merged into primary finding {primary.id} "
                        f"({primary.attribute_or_subgroup}): this cell describes "
                        f"{member_group}, which overlaps the primary's subgroup "
                        f"{primary_group}. It is kept visible but not counted as a "
                        "second bias finding."
                    )
                else:
                    direct = p_value is not None and p_value >= alpha
                    comparison = (
                        "statistically indistinguishable from the primary"
                        if direct
                        else "statistically indistinguishable from another cell in "
                        "the same sibling cluster"
                    )
                    detail = (
                        f"sibling context {member_group} shares treatment "
                        f"{member.treatment}={member.treatment_level} with primary "
                        f"{primary.id}; confirmation net is {comparison} "
                        f"(z-test vs primary p={p_value:.3f})"
                    )
                    reason = (
                        f"Merged into primary finding {primary.id} "
                        f"({primary.attribute_or_subgroup}): this cell is a sibling "
                        f"context under the same treatment "
                        f"{member.treatment}={member.treatment_level}, and its "
                        f"confirmation net is {comparison} (two-sided z vs primary "
                        f"p={p_value:.3f}). It is kept visible but not counted as a "
                        "second bias finding."
                    )
                member.search["redundancy"] = {
                    "passed": False,
                    "primary": primary.id,
                    "detail": detail,
                    "sibling": not nested,
                    "z_p": p_value,
                }
                member.reason = reason
                merges.append(
                    {
                        "primary": primary.id,
                        "merged": member.id,
                        "reason": reason,
                        "check": {
                            "name": "redundancy",
                            "passed": False,
                            "detail": detail,
                        },
                    }
                )

            primary.search.setdefault("merged_cells", [])
            primary.search["merged_cells"] = list(
                dict.fromkeys(
                    [*primary.search["merged_cells"], *[m.id for m in merged]]
                )
            )
            primary.search["redundancy"] = {
                "passed": True,
                "primary": primary.id,
                "merged_count": len(primary.search["merged_cells"]),
                "detail": (
                    f"primary after merging {len(primary.search['merged_cells'])} "
                    f"overlapping or sibling confirmed cell(s): "
                    f"{', '.join(primary.search['merged_cells'])}"
                ),
                "sibling_cluster": sibling_cluster,
                "common_context": dict(common),
                "re_described": re_described,
            }
            if sibling_cluster:
                primary.search["sibling_merge"] = {
                    "shared_treatment": primary.treatment,
                    "shared_level": primary.treatment_level,
                    "common_context": dict(common),
                    "members": [member.id for member in members],
                    "materially_stronger_specific": materially_stronger,
                    "re_described": re_described,
                }
            primary.reason = (
                primary.reason.rstrip()
                + f" Merged {len(merged)} overlapping or sibling cell(s) into this "
                f"primary finding: {', '.join(member.id for member in merged)}."
            )
            if re_described:
                primary.reason += (
                    " The primary is described as the shared treatment and the "
                    "narrowest common context; its evidence is the primary cell's "
                    "own confirmation sample, not a pooled estimate."
                )
            merges.append(
                {
                    "primary": primary.id,
                    "merged": None,
                    "reason": primary.search["redundancy"]["detail"],
                    "check": {
                        "name": "redundancy",
                        "passed": True,
                        "detail": primary.search["redundancy"]["detail"],
                    },
                }
            )
    return merges
