"""R5 Step 6: age twins on the real Adult and credit targets."""

from __future__ import annotations

import numpy as np
import pytest

from config_loader import load_config
from sandbox.generator import generate_segment, make_twin
from targets import build_target
from targets.real.features import map_applicant, probe_capabilities
from targets.real.models import load_real_model


@pytest.mark.parametrize(
    "path,model_name,real_model",
    [
        ("targets/real/uci-credit-default.yaml", "uci-credit-default", "uci_credit_default"),
        ("targets/real/adult-income.yaml", "adult-income", "adult_income"),
    ],
)
def test_real_targets_declare_age_as_a_generalized_treatment(
    path, model_name, real_model
):
    adapter = build_target(path, load_config())
    assert adapter.name == model_name
    assert adapter.real_model == real_model
    # The frozen single-attribute probe set is unchanged.
    assert adapter.supported_probes == {"gender"}
    assert adapter.supported_treatments == frozenset({"gender", "age"})
    assert adapter.treatment_supported("age")
    assert adapter.treatment_supported("gender")
    assert not adapter.treatment_supported("pincode_group")
    assert not adapter.treatment_supported("name_group")


@pytest.mark.parametrize(
    "model_name", ["uci_credit_default", "adult_income"]
)
def test_age_twin_changes_exactly_the_mapped_age_feature(model_name):
    applicants, _ = generate_segment(20, seed=31, age_band="<35")
    profile = load_real_model(model_name).profile
    for original in applicants:
        twin = make_twin(original, "age", "45+", np.random.default_rng(7))
        left = map_applicant(model_name, original, profile)
        right = map_applicant(model_name, twin, profile)
        changed = [key for key in left if left[key] != right[key]]
        assert changed == ["age"]
        assert left["age"] != right["age"]


@pytest.mark.parametrize(
    "model_name", ["uci_credit_default", "adult_income"]
)
def test_real_validate_pair_accepts_age_and_gender_twins(model_name):
    from targets.real.features import validate_pair

    profile = load_real_model(model_name).profile
    original = generate_segment(1, seed=41, age_band="<35", gender="female")[0][0]
    age_twin = make_twin(original, "age", "45+", np.random.default_rng(9))
    feasible, reason = validate_pair(
        model_name, original, age_twin, "age", profile
    )
    assert feasible, reason

    gender_twin = make_twin(
        original, "gender", "male", np.random.default_rng(9)
    )
    feasible, reason = validate_pair(
        model_name, original, gender_twin, "gender", profile
    )
    assert feasible, reason


def test_real_capabilities_expose_the_generalized_treatments():
    for model_name in ("uci_credit_default", "adult_income"):
        capabilities = probe_capabilities(model_name)
        assert capabilities["supported_probes"] == ["gender"]
        assert capabilities["supported_treatments"] == ["gender", "age"]


def test_http_adapter_parses_supported_treatments():
    from targets.http import HTTPTargetAdapter

    spec = {
        "name": "declared",
        "base_url": "http://127.0.0.1:9999",
        "request": {"method": "POST", "path": "/score_batch", "body": "${applicants}"},
        "response": {"items": "$", "approved": "approved", "score": "score"},
        "capabilities": {"supported_probes": ["gender"], "supported_treatments": ["age"]},
    }
    adapter = HTTPTargetAdapter(spec)
    assert adapter.supported_probes == {"gender"}
    assert adapter.supported_treatments == {"age"}
    assert adapter.describe()["supported_treatments"] == ["age"]
