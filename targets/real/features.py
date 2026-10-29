"""Canonical ``Applicant`` -> real-dataset feature mapping.

Both real models were trained on public data whose columns do not match the
canonical applicant contract. The mapping here is fixed before any audit and is
recorded in each model's ``metrics.json`` (quantile grids, ranges, categories).

Design rules
------------
- The protected attribute is a natural model input: ``sex`` is a feature in
  both models, because a practitioner training on this data would normally
  include it. This is recorded in DECISIONS.md D-019.
- Numeric canonical fields are mapped with a monotone empirical-quantile
  transform into the dataset's observed distribution. The transform is
  deterministic and depends only on the canonical value, so two applicants
  that differ only in gender still differ only in ``sex`` after mapping.
- Dataset columns the canonical contract cannot supply are set to a documented
  constant (training mode/median). That is an approximation, not observed data,
  and each one is listed in ``UNSUPPORTED_FIELDS`` or ``CONSTANT_FIELDS``.
- Nothing here reads a protected attribute from anywhere except the canonical
  ``Applicant``. There is no inference of race, caste, or religion.

Feasibility
-----------
``map_applicant`` returns the exact feature row sent to the model.
``validate_row`` checks it against the training ranges/vocabularies.
``validate_pair`` additionally asserts that a gender twin changes only ``sex``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from schemas import Applicant

# Source ranges for the canonical fields, from sandbox.generator (income can
# reach roughly 8m after the group multipliers).
SOURCE_RANGES: dict[str, tuple[float, float]] = {
    "income": (120_000.0, 8_000_000.0),
    "loan_amount": (25_000.0, 5_000_000.0),
    "credit_score": (300.0, 900.0),
    "employment_years": (0.0, 45.0),
    "age": (21.0, 65.0),
}

CREDIT_FEATURES = [
    "limit_bal",
    "sex",
    "education",
    "marriage",
    "age",
    "pay_0",
    "pay_2",
    "pay_3",
    "pay_4",
    "pay_5",
    "pay_6",
    "bill_amt1",
    "bill_amt2",
    "bill_amt3",
    "bill_amt4",
    "bill_amt5",
    "bill_amt6",
    "pay_amt1",
    "pay_amt2",
    "pay_amt3",
    "pay_amt4",
    "pay_amt5",
    "pay_amt6",
]

ADULT_NUMERIC = [
    "age",
    "fnlwgt",
    "education_num",
    "capital_gain",
    "capital_loss",
    "hours_per_week",
]
ADULT_CATEGORICAL = [
    "workclass",
    "education",
    "marital_status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "native_country",
]
ADULT_FEATURES = ADULT_NUMERIC + ADULT_CATEGORICAL

PROBE_SUPPORT: dict[str, tuple[list[str], dict[str, str]]] = {
    "gender": (["gender"], {}),
}

UNSUPPORTED_PROBE_REASONS = {
    "pincode_group": (
        "Dataset has no pincode or region column; the model was trained "
        "without one, so a pincode twin cannot change any input feature."
    ),
    "name_group": (
        "Dataset has no applicant-name column; the model was trained without "
        "a name, so a name twin cannot change any input feature."
    ),
    "intersectional": (
        "Intersectional cells require urban/rural; neither real dataset has "
        "that column, so the cell probes are not defined."
    ),
}

# Canonical fields each model actually consumes.
USED_FIELDS: dict[str, list[str]] = {
    "uci_credit_default": [
        "income",
        "loan_amount",
        "credit_score",
        "age",
        "gender",
    ],
    "adult_income": ["age", "gender", "credit_score", "employment_years"],
}

UNUSED_FIELDS: dict[str, list[str]] = {
    "uci_credit_default": [
        "employment_years",
        "pincode",
        "name",
        "pincode_group",
        "name_group",
        "urban_rural",
        "age_band",
        "id",
    ],
    "adult_income": [
        "income",
        "loan_amount",
        "pincode",
        "name",
        "pincode_group",
        "name_group",
        "urban_rural",
        "age_band",
        "id",
    ],
}

# Dataset columns that are fixed because the canonical contract has no source
# for them. Recorded in the README and in metrics.json.
CONSTANT_FIELDS: dict[str, dict[str, Any]] = {
    "uci_credit_default": {
        "marriage": 2,
        "education_source": "credit_score thresholds 750/650 -> 1/2/3",
        "payment_delay_source": "clip(round((700 - credit_score) / 55), -2, 8)",
    },
    "adult_income": {
        "workclass": "Private",
        "marital_status": "Never-married",
        "occupation": "Prof-specialty",
        "relationship": "Not-in-family",
        "race": "White",
        "native_country": "United-States",
        "capital_gain": 0,
        "capital_loss": 0,
        "fnlwgt": "training median",
        "education_source": "credit_score thresholds 750/650 -> Masters/Bachelors/HS-grad",
        "hours_per_week_source": "employment_years quantile-mapped to the training range",
    },
}


def _percentiles(grid: list[float]) -> np.ndarray:
    return np.linspace(0.0, 1.0, len(grid))


def quantile_map(
    value: float,
    source_range: tuple[float, float],
    grid: list[float],
) -> float:
    """Map a canonical value monotonically onto a training quantile grid."""

    low, high = source_range
    if high <= low:
        raise ValueError("invalid source range")
    position = (float(value) - low) / (high - low)
    position = float(np.clip(position, 0.0, 1.0))
    return float(np.interp(position, _percentiles(grid), np.asarray(grid, dtype=float)))


@dataclass(frozen=True)
class FeatureProfile:
    """Ranges, quantile grids, and vocabularies learned at training time."""

    quantile_grids: dict[str, list[float]]
    ranges: dict[str, list[float]]
    categories: dict[str, list[str]]


def credit_row(applicant: Applicant, profile: FeatureProfile) -> dict[str, Any]:
    delay = int(np.clip(round((700 - applicant.credit_score) / 55), -2, 8))
    row: dict[str, Any] = {
        "limit_bal": quantile_map(
            applicant.income, SOURCE_RANGES["income"], profile.quantile_grids["limit_bal"]
        ),
        "sex": 1 if applicant.gender == "male" else 2,
        "education": 1 if applicant.credit_score >= 750 else 2 if applicant.credit_score >= 650 else 3,
        "marriage": 2,
        "age": int(np.clip(applicant.age, 21, 79)),
    }
    for column in ("pay_0", "pay_2", "pay_3", "pay_4", "pay_5", "pay_6"):
        row[column] = delay
    for index in range(1, 7):
        row[f"bill_amt{index}"] = quantile_map(
            applicant.loan_amount,
            SOURCE_RANGES["loan_amount"],
            profile.quantile_grids[f"bill_amt{index}"],
        )
        row[f"pay_amt{index}"] = quantile_map(
            applicant.income / 12.0,
            (SOURCE_RANGES["income"][0] / 12.0, SOURCE_RANGES["income"][1] / 12.0),
            profile.quantile_grids[f"pay_amt{index}"],
        )
    return {column: row[column] for column in CREDIT_FEATURES}


def adult_row(applicant: Applicant, profile: FeatureProfile) -> dict[str, Any]:
    if applicant.credit_score >= 750:
        education, education_num = "Masters", 14
    elif applicant.credit_score >= 650:
        education, education_num = "Bachelors", 13
    else:
        education, education_num = "HS-grad", 9
    return {
        "age": int(np.clip(applicant.age, 17, 90)),
        "fnlwgt": float(profile.ranges["fnlwgt"][1]),
        "education_num": education_num,
        "capital_gain": 0,
        "capital_loss": 0,
        "hours_per_week": int(
            np.clip(
                round(
                    quantile_map(
                        applicant.employment_years,
                        SOURCE_RANGES["employment_years"],
                        profile.quantile_grids["hours_per_week"],
                    )
                ),
                1,
                99,
            )
        ),
        "workclass": "Private",
        "education": education,
        "marital_status": "Never-married",
        "occupation": "Prof-specialty",
        "relationship": "Not-in-family",
        "race": "White",
        "sex": "Male" if applicant.gender == "male" else "Female",
        "native_country": "United-States",
    }


MAPPERS = {
    "uci_credit_default": credit_row,
    "adult_income": adult_row,
}


def map_applicant(
    model: str, applicant: Applicant, profile: FeatureProfile
) -> dict[str, Any]:
    return MAPPERS[model](applicant, profile)


def validate_row(
    model: str, row: dict[str, Any], profile: FeatureProfile
) -> list[str]:
    """Return human-readable violations against the training domain."""

    violations: list[str] = []
    features = CREDIT_FEATURES if model == "uci_credit_default" else ADULT_FEATURES
    for feature in features:
        if feature not in row:
            violations.append(f"{feature}: missing")
            continue
        value = row[feature]
        if feature in profile.categories:
            if str(value) not in profile.categories[feature]:
                violations.append(
                    f"{feature}: {value!r} not in training vocabulary"
                )
            continue
        low, high = profile.ranges[feature]
        try:
            number = float(value)
        except (TypeError, ValueError):
            violations.append(f"{feature}: non-numeric value {value!r}")
            continue
        if not np.isfinite(number) or number < low or number > high:
            violations.append(
                f"{feature}: {number} outside training range [{low}, {high}]"
            )
    return violations


def validate_pair(
    model: str,
    original: Applicant,
    twin: Applicant,
    attribute: str,
    profile: FeatureProfile,
) -> tuple[bool, str]:
    """Check that a twin is inside the training domain and changes one field.

    A canonical gender flip also swaps the synthetic name. Names are not model
    inputs, so the mapped feature rows must still differ in exactly ``sex``.
    """

    left = map_applicant(model, original, profile)
    right = map_applicant(model, twin, profile)
    violations = validate_row(model, left, profile) + validate_row(model, right, profile)
    if violations:
        return False, "; ".join(violations)

    changed = [key for key in left if left[key] != right[key]]
    if attribute == "gender":
        if changed != ["sex"]:
            return False, (
                "gender twin changed mapped features "
                f"{changed or 'none'}; expected exactly ['sex']"
            )
    elif attribute == "age":
        if changed != ["age"]:
            return False, (
                "age twin changed mapped features "
                f"{changed or 'none'}; expected exactly ['age']"
            )
    elif not changed:
        return False, f"{attribute} twin changed no mapped feature"
    return True, ""


def probe_capabilities(model: str) -> dict[str, Any]:
    return {
        "supported_probes": ["gender"],
        # R5 generalized protocol: age is present in both datasets and maps to
        # a real model feature, so an age twin is a valid treatment.
        "supported_treatments": ["gender", "age"],
        "unsupported_probes": {
            key: value for key, value in UNSUPPORTED_PROBE_REASONS.items()
        },
        "used_fields": USED_FIELDS[model],
        "unused_fields": UNUSED_FIELDS[model],
        "constant_fields": CONSTANT_FIELDS[model],
    }
