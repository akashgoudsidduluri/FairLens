from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from config_loader import load_config
from sandbox.api import app
from sandbox.generator import (
    NAME_POOLS,
    PINCODE_TABLE,
    generate_applicants,
    make_twin,
)
from sandbox.models import raw_score, score_applicant

CONFIG = load_config()


@pytest.fixture(scope="module")
def sample():
    return generate_applicants(2000, seed=101)


def test_generator_is_deterministic_and_complete(sample):
    applicants, labels = sample
    assert len(applicants) == len(labels) == 2000
    assert all(isinstance(x, bool) for x in labels)
    again, labels2 = generate_applicants(2000, seed=101)
    assert [a.model_dump() for a in applicants] == [a.model_dump() for a in again]
    assert labels == labels2
    for a in applicants[:100]:
        assert a.pincode in PINCODE_TABLE
        assert a.pincode_group == PINCODE_TABLE[a.pincode]["group"]
        assert a.urban_rural == PINCODE_TABLE[a.pincode]["urban_rural"]
        assert a.name in NAME_POOLS[(a.name_group, a.gender)]
        assert a.age_band == ("<35" if a.age < 35 else "35-44" if a.age <= 44 else "45+")


def test_generated_indian_population_mix(sample):
    applicants, _ = sample
    female_share = np.mean([a.gender == "female" for a in applicants])
    rural_share = np.mean([a.urban_rural == "rural" for a in applicants])
    old_share = np.mean([a.age >= 45 for a in applicants])
    hotspot_share = np.mean(
        [a.gender == "female" and a.age >= 45 and a.urban_rural == "rural" for a in applicants]
    )
    assert 0.45 < female_share < 0.55
    assert 0.16 < rural_share < 0.24
    assert 0.16 < old_share < 0.24
    assert 0.012 < hotspot_share < 0.028


def test_gender_twin_changes_only_gender_and_name(sample):
    applicants, _ = sample
    a = next(x for x in applicants if x.gender == "male")
    twin = make_twin(a, "gender", "female", np.random.default_rng(0))
    assert twin.gender == "female"
    assert twin.name_group == a.name_group
    assert twin.name in NAME_POOLS[(a.name_group, "female")]
    diff = {
        k for k, v in a.model_dump().items() if v != twin.model_dump()[k]
    }
    assert diff == {"id", "gender", "name"}


def test_pincode_twin_preserves_urban_rural(sample):
    applicants, _ = sample
    a = next(
        x for x in applicants if x.pincode_group == "P1" and x.pincode_group != "P2"
    )
    twin = make_twin(a, "pincode_group", "P2", np.random.default_rng(0))
    assert twin.pincode_group == "P2"
    assert twin.urban_rural == a.urban_rural
    assert PINCODE_TABLE[twin.pincode]["group"] == "P2"
    diff = {k for k, v in a.model_dump().items() if v != twin.model_dump()[k]}
    assert diff == {"id", "pincode", "pincode_group"}


def test_name_twin_changes_only_name(sample):
    applicants, _ = sample
    a = next(x for x in applicants if x.name_group == "N1")
    twin = make_twin(a, "name_group", "N2", np.random.default_rng(0))
    assert twin.name_group == "N2"
    assert twin.gender == a.gender
    assert twin.name in NAME_POOLS[("N2", a.gender)]
    diff = {k for k, v in a.model_dump().items() if v != twin.model_dump()[k]}
    assert diff == {"id", "name", "name_group"}


def test_model2_penalty_is_gender_only(sample):
    applicants, _ = sample
    a = next(x for x in applicants if x.gender == "male")
    twin = make_twin(a, "gender", "female", np.random.default_rng(1))
    male = score_applicant(2, a, CONFIG).score
    female = score_applicant(2, twin, CONFIG).score
    assert male == pytest.approx(score_applicant(1, a, CONFIG).score)
    assert female == pytest.approx(male - CONFIG["models"]["penalty_gender"])
    # A non-female twin under model 3/4 keeps the base score.
    assert score_applicant(3, a, CONFIG).score == pytest.approx(
        score_applicant(1, a, CONFIG).score
    )


def test_model5_penalty_only_in_hotspot(sample):
    applicants, _ = sample
    hotspot = next(
        x for x in applicants if x.gender == "female" and x.age >= 45 and x.urban_rural == "rural"
    )
    control_female_young = next(
        x for x in applicants if x.gender == "female" and x.age < 35 and x.urban_rural == "urban"
    )
    control_male_old_rural = next(
        x for x in applicants if x.gender == "male" and x.age >= 45 and x.urban_rural == "rural"
    )
    p = CONFIG["models"]["penalty_intersectional"]
    assert score_applicant(5, hotspot, CONFIG).score == pytest.approx(
        score_applicant(1, hotspot, CONFIG).score - p
    )
    assert score_applicant(5, control_female_young, CONFIG).score == pytest.approx(
        score_applicant(1, control_female_young, CONFIG).score
    )
    assert score_applicant(5, control_male_old_rural, CONFIG).score == pytest.approx(
        score_applicant(1, control_male_old_rural, CONFIG).score
    )


def test_model7_never_uses_signal_attributes(sample):
    applicants, _ = sample
    picks = [
        next(x for x in applicants if x.gender == "male"),
        next(x for x in applicants if x.pincode_group == "P1" and x.urban_rural == "urban"),
        next(x for x in applicants if x.name_group == "N1"),
    ]
    for a, attr, target in [
        (picks[0], "gender", "female"),
        (picks[1], "pincode_group", "P2"),
        (picks[2], "name_group", "N2"),
    ]:
        twin = make_twin(a, attr, target, np.random.default_rng(2))
        r1 = score_applicant(7, a, CONFIG)
        r2 = score_applicant(7, twin, CONFIG)
        assert r1.approved == r2.approved
        assert r1.score == pytest.approx(r2.score)


def test_model7_has_observational_income_gap():
    applicants, _ = generate_applicants(4000, seed=7)
    female = [score_applicant(7, a, CONFIG).approved for a in applicants if a.gender == "female"]
    male = [score_applicant(7, a, CONFIG).approved for a in applicants if a.gender == "male"]
    gap = float(np.mean(male) - np.mean(female))
    assert gap > 0.05, gap


def test_model6_noise_reproducible_and_balanced(sample):
    applicants, _ = sample
    a = next(x for x in applicants if x.gender == "male")
    twin = make_twin(a, "gender", "female", np.random.default_rng(3))
    assert score_applicant(6, a, CONFIG).score == score_applicant(6, a, CONFIG).score
    flipped = 0
    total = 0
    for x in applicants[:500]:
        if x.gender != "male":
            continue
        t = make_twin(x, "gender", "female", np.random.default_rng(4))
        r1 = score_applicant(6, x, CONFIG).approved
        r2 = score_applicant(6, t, CONFIG).approved
        total += 1
        flipped += int(r1 != r2)
    assert total > 100
    assert 0.2 < flipped / total < 0.8


def test_api_health_score_batch_and_validation(sample):
    applicants, _ = sample
    client = TestClient(app)
    assert client.get("/health").json()["models"] == 7
    r = client.post("/score?model=1", json=applicants[0].model_dump())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"approved", "score"}
    batch = client.post(
        "/score_batch?model=2", json=[a.model_dump() for a in applicants[:10]]
    )
    assert batch.status_code == 200
    assert len(batch.json()) == 10
    assert client.post("/score?model=8", json=applicants[0].model_dump()).status_code == 422
    assert client.get("/health").json()["synthetic"] is True


def test_base_score_formula_matches_documented_formula(sample):
    applicants, _ = sample
    for a in applicants[:20]:
        m = CONFIG["models"]
        income_norm = max(
            0.0,
            min(
                1.0,
                math.log(a.income / m["income_floor"])
                / math.log(m["income_ceiling"] / m["income_floor"]),
            ),
        )
        expected = (
            m["base_intercept"]
            + m["base_income_weight"] * income_norm
            + m["base_credit_weight"] * ((a.credit_score - 300) / 600)
            + m["base_employment_weight"] * min(1.0, a.employment_years / 15)
            + m["base_burden_weight"] * max(0.0, min(1.0, 1 - (a.loan_amount / a.income) / 2.5))
        )
        assert raw_score(1, a, CONFIG) == pytest.approx(expected)
