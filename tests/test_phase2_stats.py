from __future__ import annotations

import math

import pytest
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

from auditor.skeptic import review
from auditor.statistician import (
    bootstrap_net_flip_ci,
    holm_adjust,
    mcnemar_exact,
    newcombe_gap_ci,
    paired_evidence,
    wilson_interval,
)
from config_loader import load_config
from schemas import Evidence, Finding

CONFIG = load_config()


def test_mcnemar_matches_statsmodels_exact():
    for b, c in [(10, 2), (0, 0), (5, 5), (40, 7), (1, 20)]:
        expected = mcnemar([[0, b], [c, 0]], exact=True, correction=False).pvalue
        assert mcnemar_exact(b, c) == pytest.approx(float(expected), rel=1e-12, abs=1e-15)


def test_wilson_matches_statsmodels():
    for k, n in [(30, 100), (0, 50), (50, 50), (3, 17), (1, 1000)]:
        assert wilson_interval(k, n) == pytest.approx(
            proportion_confint(k, n, method="wilson"), abs=1e-12
        )


def test_newcombe_gap_matches_statsmodels():
    for k1, n1, k2, n2 in [(70, 100, 40, 100), (5, 20, 2, 25), (0, 30, 10, 30)]:
        ours = newcombe_gap_ci(k1, n1, k2, n2)
        theirs = confint_proportions_2indep(
            k1, n1, k2, n2, method="newcomb", compare="diff"
        )
        assert ours == pytest.approx(tuple(float(x) for x in theirs), abs=1e-10)


def test_holm_matches_statsmodels():
    pvals = [0.01, 0.02, 0.03, 0.2, 0.0004]
    expected = multipletests(pvals, method="holm")[1]
    assert holm_adjust(pvals) == pytest.approx(list(expected), abs=1e-12)
    assert holm_adjust([]) == []


def test_bootstrap_ci_close_to_analytic_wald_for_large_sample():
    b, c, n = 240, 60, 2000
    d = (b - c) / n
    variance = (b + c) / n - d * d
    se = math.sqrt(variance / n)
    analytic = (d - 1.96 * se, d + 1.96 * se)
    low, high = bootstrap_net_flip_ci(b, c, n, iterations=6000, seed_key="test-ci")
    assert low == pytest.approx(analytic[0], abs=0.015)
    assert high == pytest.approx(analytic[1], abs=0.015)
    assert low < d < high


def test_bootstrap_is_seeded():
    a = bootstrap_net_flip_ci(40, 10, 1000, iterations=500, seed_key="x")
    b = bootstrap_net_flip_ci(40, 10, 1000, iterations=500, seed_key="x")
    assert a == b
    c = bootstrap_net_flip_ci(40, 10, 1000, iterations=500, seed_key="y")
    assert a != c


def test_paired_evidence_consistency():
    ev = paired_evidence(40, 10, 1000, seed_key="p")
    assert ev.net_flip_rate == pytest.approx(0.03)
    assert ev.b == 40 and ev.c == 10
    assert ev.p_raw < 0.001
    assert ev.ci_low <= ev.net_flip_rate <= ev.ci_high
    assert ev.p_adjusted == ev.p_raw


def _finding(b, c, p_adj, net, gap, matched=None, n=2000):
    ev = Evidence(
        n=n,
        b=b,
        c=c,
        net_flip_rate=net,
        ci_low=max(-1.0, net - 0.01),
        ci_high=min(1.0, net + 0.01),
        p_raw=p_adj,
        p_adjusted=p_adj,
    )
    return Finding(
        id="test",
        kind="single_attribute",
        attribute_or_subgroup="gender=female",
        target_group="female",
        comparison_group="male",
        evidence=ev,
        observational_gap=gap,
        status="candidate",
        matched_evidence=matched,
    )


def test_skeptic_keeps_significant_material_persistent_effect():
    matched = Evidence(
        n=1000,
        b=100,
        c=5,
        net_flip_rate=0.095,
        ci_low=0.075,
        ci_high=0.115,
        p_raw=1e-6,
        p_adjusted=1e-6,
    )
    verdict = review(_finding(200, 10, 1e-9, 0.095, 0.30), CONFIG, matched)
    assert verdict.final_status == "kept"
    assert all(check.passed for check in verdict.checks)


def test_skeptic_marks_sub_materiality_as_immaterial():
    verdict = review(_finding(30, 10, 0.01, 0.01, 0.30), CONFIG)
    assert verdict.final_status == "immaterial"
    assert "immaterial" in verdict.reason.lower()


def test_skeptic_rejects_confounded_gap():
    verdict = review(_finding(0, 0, 1.0, 0.0, 0.20), CONFIG)
    assert verdict.final_status == "rejected"
    assert "confound" in verdict.reason.lower() or "legitimate" in verdict.reason.lower()
    confound = next(c for c in verdict.checks if c.name == "confounding_check")
    assert confound.passed is False


def test_skeptic_rejects_when_income_matched_effect_disappears():
    matched = Evidence(
        n=1000,
        b=10,
        c=10,
        net_flip_rate=0.0,
        ci_low=-0.02,
        ci_high=0.02,
        p_raw=1.0,
        p_adjusted=1.0,
    )
    verdict = review(_finding(200, 10, 1e-9, 0.095, 0.30), CONFIG, matched)
    assert verdict.final_status == "rejected"
    assert "income-matched" in verdict.reason.lower()


def test_skeptic_rejects_noise_like_b_about_c():
    verdict = review(_finding(200, 195, 0.9, 0.0025, 0.01), CONFIG)
    assert verdict.final_status == "rejected"


def test_skeptic_reports_every_check():
    verdict = review(_finding(0, 0, 1.0, 0.0, 0.20), CONFIG)
    names = [c.name for c in verdict.checks]
    assert names == [
        "min_sample_size",
        "significance_after_correction",
        "materiality",
        "symmetric_noise",
        "income_matched_persistence",
        "confounding_check",
    ]
