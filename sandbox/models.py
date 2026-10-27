"""Private sandbox scoring models (models 1-7).

Never import this module from auditor code. The auditor sees only HTTP responses.

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


def _noise(applicant: Applicant, config: dict[str, Any]) -> float:
    """Deterministic per-applicant noise: hash(seed, applicant) -> Gaussian draw.

    Same applicant in the same run gets the same noise, so a whole audit is
    reproducible from the configured seed and a retried request returns the same
    score. Different twins get independent draws.
    """

    m = config["models"]
    payload = f"{m['noise_seed']}|{applicant.id}|{applicant.model_dump_json()}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    return float(np.random.default_rng(seed).normal(0.0, m["noise_sd"]))


def raw_score(model_id: int, applicant: Applicant, config: dict[str, Any]) -> float:
    m = config["models"]
    if model_id == 7:
        z = (math.log(applicant.income) - math.log(m["income_only_reference_income"])) / m[
            "income_only_log_scale"
        ]
        return m["income_only_intercept"] + m["income_only_slope"] * z

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
        raise ValueError(f"unknown model id: {model_id} (expected 1..7)")
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
