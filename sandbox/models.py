"""Private sandbox scoring models (models 1-15).

Never import this module from auditor code. The auditor sees only HTTP responses.
Models 1-7 are validation suite A. Models 8-14 are validation suite B and Model
15 is the clean control B; their planted behaviour is frozen in
``expected_findings.md`` and their coefficients live in ``config.yaml`` under
``suite_b``.

Base score for models 1-6 (all coefficients come from config.yaml):

    income_norm    = clip(log(income / floor) / log(ceiling / floor), 0, 1)
    credit_norm    = (credit_score - 300) / 600
    employment_norm= clip(employment_years / 15, 0, 1)
    burden_norm    = clip(1 - (loan_amount / income) / 2.5, 0, 1)
    base = intercept
           + w_income * income_norm
           + w_credit * credit_norm
           + w_employment * employment_norm
           + w_burden * burden_norm

Approve iff score >= approval_threshold. Each planted penalty is subtracted from
the base score in the relevant subgroup. Model 6 adds deterministic
per-applicant Gaussian noise (independent across twins, stable across retries).
Model 7 uses income alone.

The API must not reveal which model has which penalty.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np

from schemas import Applicant, ModelResponse


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def base_score(applicant: Applicant, config: dict[str, Any]) -> float:
    m = config["models"]
    income_norm = _clip(
        math.log(applicant.income / m["income_floor"])
        / math.log(m["income_ceiling"] / m["income_floor"])
    )
    credit_norm = (applicant.credit_score - 300) / 600.0
    employment_norm = _clip(applicant.employment_years / 15.0)
    burden_norm = _clip(1.0 - (applicant.loan_amount / applicant.income) / 2.5)
    return (
        m["base_intercept"]
        + m["base_income_weight"] * income_norm
        + m["base_credit_weight"] * credit_norm
        + m["base_employment_weight"] * employment_norm
        + m["base_burden_weight"] * burden_norm
    )


def _noise_for(
    applicant: Applicant, noise_seed: int, noise_sd: float
) -> float:
    payload = f"{noise_seed}|{applicant.id}|{applicant.model_dump_json()}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    return float(np.random.default_rng(seed).normal(0.0, noise_sd))


def _noise(applicant: Applicant, config: dict[str, Any]) -> float:
    """Deterministic per-applicant noise: hash(seed, applicant) -> Gaussian draw.

    Same applicant in the same run gets the same noise, so a whole audit is
    reproducible from the configured seed and a retried request returns the same
    score. Different twins get independent draws.
    """

    m = config["models"]
    return _noise_for(applicant, int(m["noise_seed"]), float(m["noise_sd"]))


def _control_b_score(applicant: Applicant, config: dict[str, Any]) -> float:
    """Clean control B: base score plus legitimate interactions and noise.

    The interactions only use legitimate credit features. Income is correlated
    with the protected groups through the frozen generator, so a naive auditor
    can see observational gaps, but no group term exists and a same-applicant
    twin flip changes nothing in this score.
    """

    m = config["models"]
    s = config["suite_b"]
    income_norm = _clip(
        math.log(applicant.income / m["income_floor"])
        / math.log(m["income_ceiling"] / m["income_floor"])
    )
    credit_norm = (applicant.credit_score - 300) / 600.0
    employment_norm = _clip(applicant.employment_years / 15.0)
    burden_norm = _clip(1.0 - (applicant.loan_amount / applicant.income) / 2.5)
    age_norm = _clip((applicant.age - 21) / (65 - 21))
    score = base_score(applicant, config)
    score += s["control_income_credit_weight"] * income_norm * credit_norm
    score += s["control_burden_employment_weight"] * burden_norm * employment_norm
    score += s["control_age_credit_weight"] * age_norm * credit_norm
    score += _noise_for(
        applicant,
        int(s["control_noise_seed"]),
        float(s["control_noise_sd"]),
    )
    return float(score)


def _suite_b_score(
    model_id: int, applicant: Applicant, config: dict[str, Any]
) -> float:
    """Planted suite B behaviour (models 8-14) on the shared base score."""

    s = config["suite_b"]
    if model_id == 15:
        return _control_b_score(applicant, config)

    score = base_score(applicant, config)
    if model_id == 8:
        if applicant.age >= s["age_55_threshold"]:
            score -= s["age_55_penalty"]
    elif model_id == 9:
        if applicant.pincode_group == "P2" and applicant.gender == "female":
            score -= s["pincode_female_penalty"]
    elif model_id == 10:
        if applicant.name_group == "N2" and applicant.age_band == "45+":
            score -= s["name_age45_penalty"]
    elif model_id == 11:
        if (
            applicant.pincode_group == "P2"
            and applicant.loan_amount >= s["high_loan_threshold"]
        ):
            score -= s["pincode_high_loan_penalty"]
    elif model_id == 12:
        if (
            applicant.gender == "female"
            and applicant.age_band == "45+"
            and applicant.urban_rural == "rural"
            and applicant.name_group == "N2"
        ):
            score -= s["female_45_rural_n2_penalty"]
    elif model_id == 13:
        years_over = max(0, applicant.age - s["age_graded_start"])
        score -= min(
            s["age_graded_cap"], s["age_graded_per_year"] * years_over
        )
    elif model_id == 14:
        if applicant.loan_amount < s["proxy_low_loan_threshold"]:
            score -= s["proxy_low_loan_penalty"]
    else:
        raise ValueError(
            f"unknown model id: {model_id} (expected 1..15)"
        )
    return float(score)


def raw_score(model_id: int, applicant: Applicant, config: dict[str, Any]) -> float:
    m = config["models"]
    if model_id == 7:
        z = (math.log(applicant.income) - math.log(m["income_only_reference_income"])) / m[
            "income_only_log_scale"
        ]
        return m["income_only_intercept"] + m["income_only_slope"] * z
    if 8 <= model_id <= 15:
        return _suite_b_score(model_id, applicant, config)

    score = base_score(applicant, config)
    if model_id == 1:
        pass
    elif model_id == 2:
        if applicant.gender == "female":
            score -= m["penalty_gender"]
    elif model_id == 3:
        if applicant.pincode_group == "P2":
            score -= m["penalty_pincode"]
    elif model_id == 4:
        if applicant.name_group == "N2":
            score -= m["penalty_name"]
    elif model_id == 5:
        if applicant.gender == "female" and applicant.age >= 45 and applicant.urban_rural == "rural":
            score -= m["penalty_intersectional"]
    elif model_id == 6:
        score += _noise(applicant, config)
    else:
        raise ValueError(f"unknown model id: {model_id} (expected 1..15)")
    return float(score)


def score_applicant(
    model_id: int, applicant: Applicant, config: dict[str, Any]
) -> ModelResponse:
    score = raw_score(model_id, applicant, config)
    return ModelResponse(
        approved=bool(score >= config["models"]["approval_threshold"]),
        score=round(score, 4),
    )


def score_batch(
    model_id: int, applicants: list[Applicant], config: dict[str, Any]
) -> list[ModelResponse]:
    return [score_applicant(model_id, applicant, config) for applicant in applicants]
