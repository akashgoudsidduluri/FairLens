"""Synthetic applicant generator for the FairLens sandbox.

NO real or personal data is used. Names are invented pools and pincodes are
synthetic labels. Group incomes differ on purpose so the confounded model has a
real observational gap. The hidden ``true_repay`` label depends only on
legitimate credit features plus noise, never on gender, pincode, or name group.

Randomness is always through an explicit ``numpy.random.Generator`` seed.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from schemas import Applicant

# 12 synthetic pincodes. P1/P2 each have one rural pincode; P3 is all urban.
# Weighted rural share = .50*.25 + .30*.25 + .20*0 = .20.
PINCODE_TABLE: dict[str, dict[str, str]] = {
    "500001": {"group": "P1", "urban_rural": "urban"},
    "500002": {"group": "P1", "urban_rural": "urban"},
    "500003": {"group": "P1", "urban_rural": "urban"},
    "500004": {"group": "P1", "urban_rural": "rural"},
    "500010": {"group": "P2", "urban_rural": "urban"},
    "500011": {"group": "P2", "urban_rural": "urban"},
    "500012": {"group": "P2", "urban_rural": "urban"},
    "500013": {"group": "P2", "urban_rural": "rural"},
    "500020": {"group": "P3", "urban_rural": "urban"},
    "500021": {"group": "P3", "urban_rural": "urban"},
    "500022": {"group": "P3", "urban_rural": "urban"},
    "500023": {"group": "P3", "urban_rural": "urban"},
}

PINCODE_TO_GROUP: dict[str, str] = {p: v["group"] for p, v in PINCODE_TABLE.items()}
PINCODE_URBAN_RURAL: dict[str, str] = {p: v["urban_rural"] for p, v in PINCODE_TABLE.items()}

# Invented name pools. These are synthetic labels, not a mapping to any real
# caste, religion, or community.
NAME_POOLS: dict[tuple[str, str], list[str]] = {
    ("N1", "female"): ["Aaravi", "Meghana", "Tanvi", "Ira", "Nitya", "Saanvi", "Kavya", "Riya", "Anika", "Diya"],
    ("N1", "male"): ["Aarav", "Meghan", "Tanay", "Ishaan", "Nikhil", "Sarthak", "Kabir", "Rohan", "Anik", "Dev"],
    ("N2", "female"): ["Charuni", "Dhanvi", "Lavanya", "Mihira", "Nandita", "Pallavi", "Shravya", "Varsha", "Yamini", "Zoya"],
    ("N2", "male"): ["Chandan", "Dhanush", "Lakshan", "Mihir", "Nandan", "Pranav", "Shravan", "Varun", "Yash", "Zubin"],
    ("N3", "female"): ["Esha", "Gauri", "Jahnavi", "Kritika", "Mira", "Naina", "Ovi", "Prisha", "Saira", "Tara"],
    ("N3", "male"): ["Eshan", "Gaurav", "Jai", "Kiran", "Manav", "Neel", "Om", "Parth", "Sahil", "Tarun"],
}

NAME_TO_GROUP: dict[str, str] = {
    name: group for (group, _gender), names in NAME_POOLS.items() for name in names
}

NAME_TO_GENDER: dict[str, str] = {
    name: gender for (_group, gender), names in NAME_POOLS.items() for name in names
}

GENDER_WEIGHTS = {"female": 0.5, "male": 0.5}
PINCODE_GROUP_WEIGHTS = {"P1": 0.50, "P2": 0.30, "P3": 0.20}
NAME_GROUP_WEIGHTS = {"N1": 0.40, "N2": 0.35, "N3": 0.25}
AGE_BAND_WEIGHTS = {"<35": 0.40, "35-44": 0.40, "45+": 0.20}

# Deliberate income differences by group. Used by the confounded model 7.
GENDER_INCOME_MULTIPLIER = {"female": 0.82, "male": 1.0}
PINCODE_INCOME_MULTIPLIER = {"P1": 1.15, "P2": 0.78, "P3": 0.95}
NAME_INCOME_MULTIPLIER = {"N1": 1.08, "N2": 0.80, "N3": 0.98}
URBAN_INCOME_MULTIPLIER = {"urban": 1.12, "rural": 0.88}

INCOME_MEDIAN = 600_000.0
INCOME_SIGMA = 0.55
AGE_BANDS = ("<35", "35-44", "45+")
GENDERS = ("female", "male")
URBAN_RURAL_VALUES = ("urban", "rural")


def _weighted_choice(
    rng: np.random.Generator, weights: dict[str, float], allowed: Iterable[str] | None = None
) -> str:
    keys = [k for k in weights if allowed is None or k in set(allowed)]
    if not keys:
        raise ValueError("no allowed choices")
    probs = np.array([weights[k] for k in keys], dtype=float)
    probs /= probs.sum()
    return str(rng.choice(keys, p=probs))


def age_band_for(age: int) -> str:
    if age < 35:
        return "<35"
    if age <= 44:
        return "35-44"
    return "45+"


def _generate_one(
    rng: np.random.Generator,
    seed: int,
    index: int,
    *,
    gender: str | None = None,
    age_band: str | None = None,
    urban_rural: str | None = None,
    pincode_group: str | None = None,
    name_group: str | None = None,
) -> tuple[Applicant, bool]:
    gender = gender or _weighted_choice(rng, GENDER_WEIGHTS)
    if gender not in GENDERS:
        raise ValueError(f"invalid gender: {gender}")

    name_group = name_group or _weighted_choice(rng, NAME_GROUP_WEIGHTS)
    if name_group not in NAME_GROUP_WEIGHTS:
        raise ValueError(f"invalid name_group: {name_group}")

    age_band = age_band or _weighted_choice(rng, AGE_BAND_WEIGHTS)
    if age_band == "<35":
        age = int(rng.integers(21, 35))
    elif age_band == "35-44":
        age = int(rng.integers(35, 45))
    elif age_band == "45+":
        age = int(rng.integers(45, 66))
    else:
        raise ValueError(f"invalid age_band: {age_band}")

    if urban_rural is not None and urban_rural not in URBAN_RURAL_VALUES:
        raise ValueError(f"invalid urban_rural: {urban_rural}")

    if pincode_group is not None:
        if pincode_group not in PINCODE_GROUP_WEIGHTS:
            raise ValueError(f"invalid pincode_group: {pincode_group}")
        group = pincode_group
    else:
        allowed_groups = [
            g
            for g in PINCODE_GROUP_WEIGHTS
            if urban_rural is None
            or any(
                info["group"] == g and info["urban_rural"] == urban_rural
                for info in PINCODE_TABLE.values()
            )
        ]
        group = _weighted_choice(rng, PINCODE_GROUP_WEIGHTS, allowed_groups)

    pincode_options = [
        p
        for p, info in PINCODE_TABLE.items()
        if info["group"] == group and (urban_rural is None or info["urban_rural"] == urban_rural)
    ]
    if not pincode_options:
        raise ValueError(f"no pincode for group={group}, urban_rural={urban_rural}")
    pincode = str(rng.choice(pincode_options))
    actual_urban_rural = PINCODE_URBAN_RURAL[pincode]
    name = str(rng.choice(NAME_POOLS[(name_group, gender)]))

    income = float(rng.lognormal(mean=math.log(INCOME_MEDIAN), sigma=INCOME_SIGMA))
    income *= GENDER_INCOME_MULTIPLIER[gender]
    income *= PINCODE_INCOME_MULTIPLIER[group]
    income *= NAME_INCOME_MULTIPLIER[name_group]
    income *= URBAN_INCOME_MULTIPLIER[actual_urban_rural]
    income = max(120_000.0, round(income, -3))

    loan_ratio = float(np.clip(rng.lognormal(mean=0.0, sigma=0.45), 0.30, 3.0))
    loan_amount = max(25_000.0, round(income * loan_ratio, -3))

    credit_score = int(np.clip(round(rng.normal(690, 85)), 300, 900))
    max_employment = max(0, age - 21)
    employment_years = float(
        np.clip(round(rng.gamma(shape=2.0, scale=4.0), 1), 0, max_employment)
    )

    z = (
        -0.3
        + 1.1 * (credit_score - 650) / 100.0
        + 0.9 * (math.log(income) - math.log(600_000.0)) / 0.6
        + 0.4 * (employment_years / 10.0)
        - 0.8 * ((loan_amount / income) - 1.2)
    )
    repay_prob = 1.0 / (1.0 + math.exp(-z))
    true_repay = bool(rng.random() < repay_prob)

    applicant = Applicant(
        id=f"S{seed}-{index:06d}",
        income=income,
        loan_amount=loan_amount,
        credit_score=credit_score,
        employment_years=employment_years,
        age=age,
        gender=gender,  # type: ignore[arg-type]
        pincode=pincode,
        name=name,
        pincode_group=group,  # type: ignore[arg-type]
        name_group=name_group,  # type: ignore[arg-type]
        urban_rural=actual_urban_rural,  # type: ignore[arg-type]
        age_band=age_band,  # type: ignore[arg-type]
    )
    return applicant, true_repay


def generate_applicants(n: int, seed: int = 42) -> tuple[list[Applicant], list[bool]]:
    """Generate ``n`` synthetic applicants and hidden true-repay labels.

    Income is lognormal with median 600,000 and sigma 0.55, then multiplied by
    deliberate group factors. Credit score is Normal(690, 85) clipped to
    [300, 900]. true_repay is a logistic draw from credit score, log income,
    employment years, and loan burden only (formula below); group signals are
    never used.

        z = -0.3 + 1.1*(credit-650)/100 + 0.9*(log(income)-log(600000))/0.6
            + 0.4*(employment_years/10) - 0.8*(loan_to_income - 1.2)
        P(true_repay) = 1 / (1 + exp(-z))
    """

    if n <= 0:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)
    applicants: list[Applicant] = []
    labels: list[bool] = []
    for i in range(n):
        applicant, label = _generate_one(rng, seed, i)
        applicants.append(applicant)
        labels.append(label)
    return applicants, labels


def generate_segment(
    n: int,
    seed: int = 42,
    *,
    gender: str | None = None,
    age_band: str | None = None,
    urban_rural: str | None = None,
    pincode_group: str | None = None,
    name_group: str | None = None,
) -> tuple[list[Applicant], list[bool]]:
    """Generate applicants with fixed segment attributes.

    Used for stratified intersectional cells so rare cells (e.g. female, 45+,
    rural) do not require rejection sampling from the natural population. Other
    attributes follow their natural conditional distributions.
    """

    if n <= 0:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)
    applicants: list[Applicant] = []
    labels: list[bool] = []
    for i in range(n):
        applicant, label = _generate_one(
            rng,
            seed,
            i,
            gender=gender,
            age_band=age_band,
            urban_rural=urban_rural,
            pincode_group=pincode_group,
            name_group=name_group,
        )
        applicants.append(applicant)
        labels.append(label)
    return applicants, labels


def pincodes_for_group(group: str, urban_rural: str | None = None) -> list[str]:
    return [
        p
        for p, info in PINCODE_TABLE.items()
        if info["group"] == group and (urban_rural is None or info["urban_rural"] == urban_rural)
    ]


def make_twin(
    applicant: Applicant,
    attribute: str,
    target_value: str | None = None,
    rng: np.random.Generator | None = None,
) -> Applicant:
    """Change exactly one signal while holding everything else fixed.

    - ``gender``: also changes the name to a synthetic name of the same
      name_group and the target gender (names encode gender).
    - ``pincode_group``: chooses a pincode in the target group with the SAME
      urban/rural tag.
    - ``name_group``: chooses a name in the target group with the SAME gender.

    Raises ``ValueError`` if no compatible value exists (e.g. a rural pincode
    group that has no rural pincode).
    """

    if rng is None:
        rng = np.random.default_rng(0)
    data = applicant.model_dump()

    if attribute == "gender":
        target = target_value or ("male" if applicant.gender == "female" else "female")
        if target not in {"female", "male"}:
            raise ValueError(f"invalid gender target: {target}")
        if target == applicant.gender:
            raise ValueError("twin must change gender")
        data["gender"] = target
        data["name"] = str(rng.choice(NAME_POOLS[(applicant.name_group, target)]))

    elif attribute == "pincode_group":
        target = target_value
        if target is None:
            options = [g for g in PINCODE_GROUP_WEIGHTS if g != applicant.pincode_group]
            target = str(rng.choice(options))
        if target == applicant.pincode_group:
            raise ValueError("twin must change pincode_group")
        options = pincodes_for_group(target, applicant.urban_rural)
        if not options:
            raise ValueError(
                f"no pincode in group {target} with urban_rural={applicant.urban_rural}"
            )
        pincode = str(rng.choice(options))
        data["pincode_group"] = target
        data["pincode"] = pincode
        data["urban_rural"] = PINCODE_URBAN_RURAL[pincode]

    elif attribute == "name_group":
        target = target_value
        if target is None:
            options = [g for g in NAME_GROUP_WEIGHTS if g != applicant.name_group]
            target = str(rng.choice(options))
        if target == applicant.name_group:
            raise ValueError("twin must change name_group")
        data["name_group"] = target
        data["name"] = str(rng.choice(NAME_POOLS[(target, applicant.gender)]))

    else:
        raise ValueError(f"unsupported attribute: {attribute}")

    data["id"] = f"{applicant.id}-T"
    return Applicant(**data)


def income_band(value: float, boundaries: Iterable[float]) -> int:
    """Return the 0-based income band for ``value`` given sorted boundaries."""

    bounds = list(boundaries)
    idx = int(np.searchsorted(bounds, value, side="right"))
    return min(idx, len(bounds))


def income_band_boundaries(incomes: Iterable[float], n_bands: int = 5) -> list[float]:
    """Quantile boundaries used by the Skeptic's income-matched re-test."""

    arr = np.asarray(list(incomes), dtype=float)
    quantiles = np.linspace(0, 100, n_bands + 1)[1:-1]
    return [float(x) for x in np.percentile(arr, quantiles)]
