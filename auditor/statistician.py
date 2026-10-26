"""Statistics for pair-based fairness evidence.

Every formula is stated here and cross-checked in tests against scipy /
statsmodels where an equivalent exists.

Definitions
-----------
For a twin pair, in the direction of harm to the target group:
    b = original (comparison group) approved AND twin (target group) rejected
    c = original rejected AND twin approved
    net_flip_rate = (b - c) / n

The exact McNemar test is the two-sided binomial test of b successes out of
b + c trials at p = 0.5:
    p = 2 * min(P(X <= min(b,c)), P(X >= max(b,c)))  (computed by scipy)
When b + c = 0 the p-value is 1.

The 95% CI for (b-c)/n is a seeded percentile bootstrap over the three paired
outcomes {harm, benefit, neither}, using a multinomial resample of size n.
This avoids a normal approximation at small discordant counts.

Holm adjustment:
    order p_(1) <= ... <= p_(m)
    p_adj_(i) = min(1, max_{j<=i} (m-j+1) * p_(j))
returned in the original order.

Observational rates use Wilson score intervals. The gap CI uses Newcombe's
hybrid score method (method 10 in Newcombe 1998):
    d = p1 - p2
    lower = d - sqrt((p1-l1)^2 + (u2-p2)^2)
    upper = d + sqrt((u1-p1)^2 + (p2-l2)^2)
where (l1,u1), (l2,u2) are Wilson intervals for the two independent groups.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

import numpy as np
from scipy.stats import binomtest, norm

from schemas import Evidence, Finding, ModelResponse


def _z_for_level(level: float) -> float:
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    return float(norm.ppf(1 - (1 - level) / 2))


def wilson_interval(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""

    if n <= 0:
        return 0.0, 1.0
    if not 0 <= k <= n:
        raise ValueError("require 0 <= k <= n")
    z = _z_for_level(level)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe_gap_ci(
    k1: int, n1: int, k2: int, n2: int, level: float = 0.95
) -> tuple[float, float]:
    """Newcombe hybrid score interval for p1 - p2 (independent groups)."""

    if n1 <= 0 or n2 <= 0:
        return -1.0, 1.0
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson_interval(k1, n1, level)
    l2, u2 = wilson_interval(k2, n2, level)
    d = p1 - p2
    low = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    high = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return max(-1.0, low), min(1.0, high)


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value: binomial test of b vs b+c at 0.5."""

    if b < 0 or c < 0:
        raise ValueError("b and c must be non-negative")
    trials = b + c
    if trials == 0:
        return 1.0
    return float(binomtest(b, trials, 0.5, alternative="two-sided").pvalue)


def _seed_int(seed_key: str) -> int:
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def bootstrap_net_flip_ci(
    b: int,
    c: int,
    n: int,
    *,
    iterations: int = 4000,
    level: float = 0.95,
    seed_key: str = "fairlens",
) -> tuple[float, float]:
    """Seeded percentile bootstrap CI for (b-c)/n over paired outcomes."""

    if n <= 0:
        return 0.0, 0.0
    if b + c > n:
        raise ValueError("b+c cannot exceed n")
    probs = np.array([b / n, c / n, max(0.0, 1 - (b + c) / n)], dtype=float)
    probs /= probs.sum()
    rng = np.random.default_rng(_seed_int(seed_key))
    draws = rng.multinomial(n, probs, size=iterations)
    deltas = (draws[:, 0] - draws[:, 1]) / n
    alpha = (1 - level) / 2
    low, high = np.quantile(deltas, [alpha, 1 - alpha])
    return float(max(-1.0, low)), float(min(1.0, high))


def paired_evidence(
    b: int,
    c: int,
    n: int,
    *,
    seed_key: str,
    iterations: int = 4000,
    level: float = 0.95,
    p_adjusted: float | None = None,
) -> Evidence:
    """Build paired evidence, including exact McNemar p and bootstrap CI."""

    if n <= 0:
        raise ValueError("n must be positive")
    if b + c > n:
        raise ValueError("b+c cannot exceed n")
    net = (b - c) / n
    ci_low, ci_high = bootstrap_net_flip_ci(
        b, c, n, iterations=iterations, level=level, seed_key=seed_key
    )
    p_raw = mcnemar_exact(b, c)
    return Evidence(
        n=n,
        b=b,
        c=c,
        net_flip_rate=net,
        ci_low=ci_low,
        ci_high=ci_high,
        p_raw=p_raw,
        p_adjusted=p_raw if p_adjusted is None else p_adjusted,
    )


def holm_adjust(pvalues: Iterable[float]) -> list[float]:
    """Holm step-down adjusted p-values, returned in the original order."""

    pvals = [float(p) for p in pvalues]
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [1.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * pvals[idx])
        running = max(running, value)
        adjusted[idx] = running
    return adjusted


def observational_rates(
    applicants: list[Any], responses: list[ModelResponse], attribute: str
) -> dict[str, dict[str, float]]:
    """Approval rates by group for gender, pincode_group, or name_group."""

    if len(applicants) != len(responses):
        raise ValueError("applicants and responses must have the same length")
    valid = {"gender", "pincode_group", "name_group"}
    if attribute not in valid:
        raise ValueError(f"attribute must be one of {valid}")
    buckets: dict[str, list[bool]] = {}
    for applicant, response in zip(applicants, responses):
        key = str(getattr(applicant, attribute))
        buckets.setdefault(key, []).append(bool(response.approved))
    return _rate_table(buckets)


def _rate_table(buckets: dict[str, list[bool]]) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = {}
    for key, values in sorted(buckets.items()):
        n = len(values)
        approvals = int(sum(values))
        low, high = wilson_interval(approvals, n)
        table[key] = {
            "n": n,
            "approvals": approvals,
            "rate": approvals / n if n else 0.0,
            "ci_low": low,
            "ci_high": high,
        }
    return table


def choose_target_group(rates: dict[str, dict[str, float]]) -> tuple[str, str]:
    """Lowest-approval group = target; highest-approval = comparison."""

    usable = {k: v for k, v in rates.items() if v["n"] > 0}
    if len(usable) < 2:
        raise ValueError("need at least two non-empty groups")
    target = min(usable, key=lambda k: (usable[k]["rate"], k))
    comparison = max(usable, key=lambda k: (usable[k]["rate"], k))
    return target, comparison


def observational_gap(
    rates: dict[str, dict[str, float]], target: str, comparison: str, level: float = 0.95
) -> dict[str, float]:
    """Gap = comparison rate - target rate, with Newcombe CI."""

    t = rates[target]
    c = rates[comparison]
    gap = c["rate"] - t["rate"]
    low, high = newcombe_gap_ci(
        int(c["approvals"]), int(c["n"]), int(t["approvals"]), int(t["n"]), level
    )
    return {"gap": gap, "ci_low": low, "ci_high": high}


def intersectional_observational_rates(
    applicants: list[Any], responses: list[ModelResponse]
) -> dict[str, dict[str, dict[str, float]]]:
    """Observed approval rates for the 12 gender x age_band x urban cells."""

    if len(applicants) != len(responses):
        raise ValueError("applicants and responses must have the same length")
    buckets: dict[str, dict[str, list[bool]]] = {}
    for applicant, response in zip(applicants, responses):
        cell = f"{applicant.gender}|{applicant.age_band}|{applicant.urban_rural}"
        buckets.setdefault(cell, {}).setdefault(applicant.gender, []).append(
            bool(response.approved)
        )
    return {cell: _rate_table(groups) for cell, groups in sorted(buckets.items())}


def _slug(value: str) -> str:
    return (
        value.replace(" ", "-")
        .replace("|", "-")
        .replace(",", "")
        .replace("=", "-")
        .replace("&", "and")
        .replace("+", "plus")
        .lower()
    )


def make_single_finding(
    attribute: str,
    target: str,
    comparison: str,
    evidence: Evidence,
    rates: dict[str, dict[str, float]],
    gap: dict[str, float],
) -> Finding:
    return Finding(
        id=f"single-{_slug(attribute)}-{_slug(target)}",
        kind="single_attribute",
        attribute_or_subgroup=f"{attribute}={target}",
        target_group=target,
        comparison_group=comparison,
        evidence=evidence,
        observational_gap=gap["gap"],
        observational_rates={
            target: rates[target]["rate"],
            comparison: rates[comparison]["rate"],
            "gap_ci_low": gap["ci_low"],
            "gap_ci_high": gap["ci_high"],
        },
        status="candidate",
        reason="Candidate from observational gap; awaiting counterfactual review.",
    )


def make_intersectional_findings(
    cells: list[dict[str, Any]],
    obs_cells: dict[str, dict[str, dict[str, float]]],
    *,
    iterations: int = 4000,
    level: float = 0.95,
    alpha: float = 0.05,
    top_k: int | None = 5,
) -> list[Finding]:
    """Holm-correct all 12 tested cells and return the top ``top_k`` by net flip.

    Each cell dict has: target_gender, comparison_gender, age_band,
    urban_rural, n, b, c. The p-values family is all tested cells, not just the
    reported top five.
    """

    if not cells:
        return []
    raw = [mcnemar_exact(int(cell["b"]), int(cell["c"])) for cell in cells]
    adjusted = holm_adjust(raw)

    findings: list[Finding] = []
    for cell, p_adj in zip(cells, adjusted):
        g = str(cell["target_gender"])
        age = str(cell["age_band"])
        urban = str(cell["urban_rural"])
        n = int(cell["n"])
        b = int(cell["b"])
        c = int(cell["c"])
        seed_key = f"inter-{g}-{age}-{urban}"
        evidence = paired_evidence(
            b,
            c,
            n,
            seed_key=seed_key,
            iterations=iterations,
            level=level,
            p_adjusted=p_adj,
        )
        cell_key = f"{g}|{age}|{urban}"
        obs = obs_cells.get(cell_key, {})
        target_obs = obs.get(g, {"rate": 0.0, "n": 0})
        other = "male" if g == "female" else "female"
        comp_obs = obs.get(other, {"rate": 0.0, "n": 0})
        gap = float(comp_obs["rate"] - target_obs["rate"])
        findings.append(
            Finding(
                id=f"inter-{_slug(g)}-{_slug(age)}-{urban}",
                kind="intersectional",
                attribute_or_subgroup=f"gender={g}, age_band={age}, urban_rural={urban}",
                target_group=f"{g}|{age}|{urban}",
                comparison_group=f"{other}|{age}|{urban}",
                evidence=evidence,
                observational_gap=gap,
                observational_rates={
                    g: float(target_obs["rate"]),
                    other: float(comp_obs["rate"]),
                    "target_n": float(target_obs["n"]),
                    "comparison_n": float(comp_obs["n"]),
                },
                status="candidate",
                reason="Intersectional cell candidate; awaiting Skeptic review.",
            )
        )

    findings.sort(key=lambda f: f.evidence.net_flip_rate, reverse=True)
    return findings if top_k is None else findings[:top_k]
