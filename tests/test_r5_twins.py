"""Tests for generalized twins (R5 Step 2).

Each twin changes exactly one *signal*; derived fields follow that signal
(gender twins also change the name, age twins also change the legacy age_band,
and urban/rural twins change the pincode string). No model input changes except
the signal, and infeasible twins raise instead of being scored.
"""

from __future__ import annotations

import numpy as np
import pytest

from sandbox.generator import (
    age_band_for,
    age_twin_feasible,
    generate_applicants,
    make_twin,
)


def base(**overrides):
    person = dict(
        id="S42-000001",
        income=600_000.0,
        loan_amount=300_000.0,
        credit_score=700,
        employment_years=5.0,
        age=40,
        gender="male",
        pincode="500001",
        name="Aarav",
        pincode_group="P1",
        name_group="N1",
        urban_rural="urban",
        age_band="35-44",
    )
    person.update(overrides)
    from schemas import Applicant

    return Applicant(**person)


def signal_fields(attribute: str) -> set[str]:
    if attribute == "gender":
        return {"gender"}
    if attribute == "age":
        return {"age"}
    if attribute == "pincode_group":
        return {"pincode_group"}
    if attribute == "name_group":
        return {"name_group"}
    if attribute == "urban_rural":
        return {"urban_rural"}
    raise AssertionError(attribute)


def assert_only_signal_changed(original, twin, attribute: str) -> None:
    before = original.model_dump()
    after = twin.model_dump()
    changed = {key for key in before if before[key] != after[key]}

    # Anything outside the signal and its derived fields is byte-identical.
    allowed_derived = {
        "gender": {"name"},
        "age": {"age_band"},
        "pincode_group": {"pincode", "urban_rural"},
        "name_group": {"name"},
        "urban_rural": {"pincode"},
    }[attribute]
    assert changed - {"id"} - allowed_derived == signal_fields(attribute)
    assert twin.id == f"{original.id}-T"


def test_gender_twin_changes_only_the_gender_signal():
    original = base(gender="male", name_group="N2")
    twin = make_twin(original, "gender", "female", np.random.default_rng(1))
    assert_only_signal_changed(original, twin, "gender")
    assert twin.gender == "female"
    assert twin.name_group == original.name_group


def test_pincode_twin_keeps_the_urban_rural_tag_and_changes_group():
    original = base(pincode_group="P1", pincode="500001", urban_rural="urban")
    twin = make_twin(original, "pincode_group", "P2", np.random.default_rng(2))
    assert_only_signal_changed(original, twin, "pincode_group")
    assert twin.pincode_group == "P2"
    assert twin.urban_rural == "urban"
    assert twin.pincode != original.pincode


def test_name_twin_keeps_gender_and_changes_group():
    original = base(gender="female", name_group="N1", name="Aaravi")
    twin = make_twin(original, "name_group", "N2", np.random.default_rng(3))
    assert_only_signal_changed(original, twin, "name_group")
    assert twin.name_group == "N2"
    assert twin.gender == "female"


def test_age_twin_moves_into_the_requested_band_and_keeps_everything_else():
    original = base(age=28, age_band="<35", employment_years=4.0)
    twin = make_twin(original, "age", "45+", np.random.default_rng(4))
    assert_only_signal_changed(original, twin, "age")
    assert 45 <= twin.age <= 65
    assert twin.age_band == "45+"
    assert twin.income == original.income
    assert twin.loan_amount == original.loan_amount
    assert twin.credit_score == original.credit_score
    assert twin.employment_years == original.employment_years


def test_age_twin_accepts_an_exact_age():
    original = base(age=30, age_band="<35", employment_years=3.0)
    twin = make_twin(original, "age", 56, np.random.default_rng(5))
    assert twin.age == 56
    assert twin.age_band == "45+"


def test_age_twin_respects_the_employment_bound():
    original = base(age=30, age_band="<35", employment_years=25.0)
    # 25 years of employment needs age >= 46, so no age in 35-44 is feasible.
    assert not age_twin_feasible(original, "35-44")
    with pytest.raises(ValueError, match="no feasible age"):
        make_twin(original, "age", "35-44", np.random.default_rng(6))


def test_age_twin_rejects_the_same_age():
    original = base(age=50, age_band="45+")
    with pytest.raises(ValueError, match="change age"):
        make_twin(original, "age", 50)


def test_age_band_helper_matches_the_generator_bands():
    assert age_band_for(21) == "<35"
    assert age_band_for(34) == "<35"
    assert age_band_for(35) == "35-44"
    assert age_band_for(44) == "35-44"
    assert age_band_for(45) == "45+"
    assert age_band_for(65) == "45+"


def test_urban_rural_twin_changes_only_the_proxy_signal():
    original = base(pincode_group="P1", pincode="500001", urban_rural="urban")
    twin = make_twin(original, "urban_rural", "rural", np.random.default_rng(7))
    assert_only_signal_changed(original, twin, "urban_rural")
    assert twin.urban_rural == "rural"
    assert twin.pincode_group == "P1"
    assert twin.pincode in {"500004"}


def test_urban_rural_twin_is_infeasible_for_p3_rural():
    original = base(pincode_group="P3", pincode="500020", urban_rural="urban")
    with pytest.raises(ValueError, match="no pincode"):
        make_twin(original, "urban_rural", "rural")


def test_generated_applicant_twins_are_deterministic():
    applicants, _ = generate_applicants(5, seed=42)
    original = applicants[0]
    first = make_twin(original, "age", "45+", np.random.default_rng(8))
    second = make_twin(original, "age", "45+", np.random.default_rng(8))
    assert first.model_dump() == second.model_dump()


def test_unsupported_attribute_raises():
    with pytest.raises(ValueError, match="unsupported attribute"):
        make_twin(base(), "credit_score", "low")


def test_targets_declare_supported_treatments():
    from targets.base import ALL_TREATMENTS, TargetAdapter

    class Dummy(TargetAdapter):
        name = "dummy"
        probe_cap = 10

        @property
        def probes_used(self) -> int:
            return 0

        def reset(self) -> None:
            pass

        async def health(self):
            return {"status": "ok"}

        async def score_batch(self, applicants):
            return []

    dummy = Dummy()
    assert dummy.supported_treatments == ALL_TREATMENTS
    assert dummy.treatment_supported("age")

    class NoAge(Dummy):
        supported_treatments = frozenset({"gender"})

    other = NoAge()
    assert other.treatment_supported("gender")
    assert not other.treatment_supported("age")
