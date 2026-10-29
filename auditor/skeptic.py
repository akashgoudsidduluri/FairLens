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

Status precedence: a significant but sub-materiality effect is "immaterial",
never "kept". A directional zero-effect candidate is "rejected".
"""

from __future__ import annotations

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
