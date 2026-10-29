"""Documented behaviour of sandbox models 8-15 (R5 Step 5)."""

from __future__ import annotations

import pytest

from config_loader import load_config
from sandbox.api import app
from sandbox.generator import generate_applicants, generate_segment, make_twin
from sandbox.models import raw_score, score_applicant
from schemas import Applicant

CONFIG = load_config()
SUITE_B = CONFIG["suite_b"]


def _pool(n: int = 4000, seed: int = 5) -> list[Applicant]:
    applicants, _ = generate_applicants(n, seed=seed)
    return applicants


def _first(applicants, predicate):
    for applicant in applicants:
        if predicate(applicant):
            return applicant
    raise AssertionError("no applicant matched the predicate")


def _base(applicant: Applicant) -> float:
    return score_applicant(1, applicant, CONFIG).score


def test_model_8_penalises_age_55_and_over_only():
    applicants = _pool()
    older = _first(applicants, lambda a: a.age >= SUITE_B["age_55_threshold"])
    younger = _first(applicants, lambda a: a.age < SUITE_B["age_55_threshold"])
    assert score_applicant(8, older, CONFIG).score == pytest.approx(
        _base(older) - SUITE_B["age_55_penalty"]
    )
    assert score_applicant(8, younger, CONFIG).score == pytest.approx(_base(younger))


def test_model_9_penalises_pincode_p2_and_female_only():
    applicants = _pool()
    target = _first(
        applicants, lambda a: a.pincode_group == "P2" and a.gender == "female"
    )
    p2_male = _first(
        applicants, lambda a: a.pincode_group == "P2" and a.gender == "male"
    )
    p1_female = _first(
        applicants, lambda a: a.pincode_group == "P1" and a.gender == "female"
    )
    assert score_applicant(9, target, CONFIG).score == pytest.approx(
        _base(target) - SUITE_B["pincode_female_penalty"]
    )
    assert score_applicant(9, p2_male, CONFIG).score == pytest.approx(_base(p2_male))
    assert score_applicant(9, p1_female, CONFIG).score == pytest.approx(
        _base(p1_female)
    )


def test_model_10_penalises_name_n2_and_age_45_plus_only():
    applicants = _pool()
    target = _first(
        applicants, lambda a: a.name_group == "N2" and a.age_band == "45+"
    )
    n2_young = _first(
        applicants, lambda a: a.name_group == "N2" and a.age_band != "45+"
    )
    n1_older = _first(
        applicants, lambda a: a.name_group == "N1" and a.age_band == "45+"
    )
    assert score_applicant(10, target, CONFIG).score == pytest.approx(
        _base(target) - SUITE_B["name_age45_penalty"]
    )
    assert score_applicant(10, n2_young, CONFIG).score == pytest.approx(
        _base(n2_young)
    )
    assert score_applicant(10, n1_older, CONFIG).score == pytest.approx(
        _base(n1_older)
    )


def test_model_11_penalises_pincode_p2_and_high_loan_only():
    applicants = _pool()
    target = _first(
        applicants,
        lambda a: a.pincode_group == "P2"
        and a.loan_amount >= SUITE_B["high_loan_threshold"],
    )
    p2_low = _first(
        applicants,
        lambda a: a.pincode_group == "P2"
        and a.loan_amount < SUITE_B["high_loan_threshold"],
    )
    assert score_applicant(11, target, CONFIG).score == pytest.approx(
        _base(target) - SUITE_B["pincode_high_loan_penalty"]
    )
    assert score_applicant(11, p2_low, CONFIG).score == pytest.approx(_base(p2_low))


def test_model_12_penalises_the_four_attribute_cell_only():
    applicants = _pool()
    target = _first(
        applicants,
        lambda a: a.gender == "female"
        and a.age_band == "45+"
        and a.urban_rural == "rural"
        and a.name_group == "N2",
    )
    near_miss = _first(
        applicants,
        lambda a: a.gender == "female"
        and a.age_band == "45+"
        and a.urban_rural == "rural"
        and a.name_group != "N2",
    )
    assert score_applicant(12, target, CONFIG).score == pytest.approx(
        _base(target) - SUITE_B["female_45_rural_n2_penalty"]
    )
    assert score_applicant(12, near_miss, CONFIG).score == pytest.approx(
        _base(near_miss)
    )


def test_model_13_age_graded_penalty_is_capped():
    applicants = _pool()
    for age in (30, 42, 50, 65):
        applicant = _first(applicants, lambda a, age=age: a.age == age)
        expected = min(
            SUITE_B["age_graded_cap"],
            SUITE_B["age_graded_per_year"]
            * max(0, age - SUITE_B["age_graded_start"]),
        )
        assert score_applicant(13, applicant, CONFIG).score == pytest.approx(
            _base(applicant) - expected
        )


def test_model_14_penalises_low_loan_amount_and_has_no_group_term():
    applicants = _pool()
    low_loan = _first(
        applicants, lambda a: a.loan_amount < SUITE_B["proxy_low_loan_threshold"]
    )
    high_loan = _first(
        applicants, lambda a: a.loan_amount >= SUITE_B["proxy_low_loan_threshold"]
    )
    assert score_applicant(14, low_loan, CONFIG).score == pytest.approx(
        _base(low_loan) - SUITE_B["proxy_low_loan_penalty"]
    )
    assert score_applicant(14, high_loan, CONFIG).score == pytest.approx(
        _base(high_loan)
    )
    # Flipping a group attribute does not change the score: only loan amount does.
    for attribute in ("gender", "pincode_group", "name_group"):
        twin = make_twin(low_loan, attribute, _other(low_loan, attribute), None)
        assert score_applicant(14, twin, CONFIG).score == pytest.approx(
            score_applicant(14, low_loan, CONFIG).score
        )


def test_model_15_has_interactions_but_no_group_term(monkeypatch):
    # Remove the deterministic noise so the legitimate part is directly visible.
    monkeypatch.setattr("sandbox.models._noise_for", lambda *args, **kwargs: 0.0)
    applicants = _pool()
    candidate = _first(applicants, lambda a: a.credit_score >= 700)
    # The control differs from the plain base: legitimate interactions exist.
    assert raw_score(15, candidate, CONFIG) != pytest.approx(_base(candidate))
    for attribute in ("gender", "pincode_group", "name_group"):
        twin = make_twin(candidate, attribute, _other(candidate, attribute), None)
        assert raw_score(15, twin, CONFIG) == pytest.approx(
            raw_score(15, candidate, CONFIG)
        )


def test_the_api_serves_models_8_to_15_without_disclosing_behaviour():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    applicant = _pool(10, seed=11)[0]
    for model in range(8, 16):
        response = client.post(
            f"/score?model={model}", json=applicant.model_dump()
        )
        assert response.status_code == 200
        assert set(response.json()) == {"approved", "score"}

    health = client.get("/health").json()
    assert health == {"status": "ok", "models": 15, "synthetic": True}


def _other(applicant: Applicant, attribute: str) -> str:
    if attribute == "gender":
        return "male" if applicant.gender == "female" else "female"
    if attribute == "pincode_group":
        return "P1" if applicant.pincode_group != "P1" else "P2"
    if attribute == "name_group":
        return "N1" if applicant.name_group != "N1" else "N2"
    raise ValueError(attribute)
