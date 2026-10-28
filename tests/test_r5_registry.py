"""Tests for the R5 attribute registry (Step 1)."""

from __future__ import annotations

import copy

import pytest

from auditor.registry import (
    RegistryError,
    load_registry,
    minimum_detectable_effect,
)
from config_loader import load_config
from schemas import Applicant


@pytest.fixture(scope="module")
def config() -> dict:
    return load_config()


@pytest.fixture(scope="module")
def registry(config):
    return load_registry(config)


def applicant(**overrides) -> Applicant:
    base = dict(
        id="A1",
        income=600_000.0,
        loan_amount=300_000.0,
        credit_score=700,
        employment_years=5.0,
        age=40,
        gender="female",
        pincode="500001",
        name="Aaravi",
        pincode_group="P1",
        name_group="N1",
        urban_rural="urban",
        age_band="35-44",
    )
    base.update(overrides)
    return Applicant(**base)


def test_registry_has_all_pre_registered_attributes(registry):
    assert set(registry.specs) == {
        "gender",
        "age",
        "pincode_group",
        "name_group",
        "urban_rural",
        "income",
        "credit_score",
        "loan_amount",
        "employment_years",
    }


def test_roles_match_the_pre_registration(registry):
    assert registry.get("gender").role == "protected"
    assert registry.get("pincode_group").role == "protected"
    assert registry.get("name_group").role == "protected"
    assert registry.get("age").role == "proxy"
    assert registry.get("urban_rural").role == "proxy"
    for name in ("income", "credit_score", "loan_amount", "employment_years"):
        assert registry.get(name).role == "legitimate"


def test_legitimate_attributes_are_context_only(registry):
    for name in registry.legitimate_attributes():
        spec = registry.get(name)
        assert spec.context is True
        assert spec.treatment is False


def test_treatment_attributes_are_protected_or_proxy(registry):
    assert registry.treatment_attributes() == [
        "gender",
        "age",
        "pincode_group",
        "name_group",
    ]
    for name in registry.treatment_attributes():
        assert registry.get(name).role in {"protected", "proxy"}


def test_urban_rural_is_context_only_for_the_stated_reason(registry):
    spec = registry.get("urban_rural")
    assert spec.treatment is False
    assert "P3 has no rural pincode" in spec.reason


@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("age", 21, "<35"),
        ("age", 34, "<35"),
        ("age", 35, "35-44"),
        ("age", 44, "35-44"),
        ("age", 45, "45+"),
        ("age", 65, "45+"),
        ("income", 399_999, "low"),
        ("income", 400_000, "mid"),
        ("income", 899_999, "mid"),
        ("income", 900_000, "high"),
        ("loan_amount", 199_999, "low"),
        ("loan_amount", 200_000, "mid"),
        ("loan_amount", 600_000, "high"),
        ("employment_years", 2.9, "low"),
        ("employment_years", 3, "mid"),
        ("employment_years", 8, "high"),
        ("credit_score", 599, "low"),
        ("credit_score", 600, "mid"),
        ("credit_score", 750, "high"),
    ],
)
def test_fixed_bins(registry, name, value, expected):
    assert registry.get(name).bin_value(value) == expected


def test_categorical_bins_reject_unknown_values(registry):
    with pytest.raises(RegistryError):
        registry.get("gender").bin_value("other")


def test_bin_value_and_cell_key_use_applicant_fields(registry):
    person = applicant(age=52, income=950_000, gender="male")
    assert registry.bin_value("age", person) == "45+"
    assert registry.bin_value("income", person) == "high"
    assert registry.cell_key(person, ["age", "income"]) == ("45+", "high")


def test_context_attributes_exclude_the_treatment(registry):
    contexts = registry.context_attributes("gender")
    assert "gender" not in contexts
    assert "age" in contexts
    assert "loan_amount" in contexts
    assert len(contexts) == 8


def test_deep_panel_is_within_the_registered_space(config, registry):
    panel = config["audit"]["search"]["deep_panel"]
    assert set(panel) == set(registry.treatment_attributes())
    for treatment, cells in panel.items():
        assert len(cells) == 4
        for cell in cells:
            assert cell, "an empty deep cell is the main effect, not a deep cell"
            assert treatment not in cell
            assert 2 <= len(cell) <= 3
            for name, value in cell.items():
                spec = registry.get(name)
                assert spec.context is True
                assert value in spec.choices


def test_mde_matches_the_stated_formula():
    from scipy.stats import norm

    expected = (norm.ppf(0.975) + norm.ppf(0.80)) * (0.25 / 200) ** 0.5
    assert minimum_detectable_effect(200, 0.05) == pytest.approx(expected)


def test_mde_shrinks_as_the_cell_grows():
    small = minimum_detectable_effect(200, 0.05)
    large = minimum_detectable_effect(2000, 0.05)
    assert large < small
    assert minimum_detectable_effect(0, 0.05) == 1.0


def test_invalid_role_is_rejected(config):
    broken = copy.deepcopy(config)
    broken["attributes"]["gender"]["role"] = "sensitive"
    with pytest.raises(RegistryError, match="role"):
        load_registry(broken)


def test_legitimate_attribute_cannot_be_a_treatment(config):
    broken = copy.deepcopy(config)
    broken["attributes"]["income"]["treatment"] = True
    with pytest.raises(RegistryError, match="context-only"):
        load_registry(broken)


def test_band_edges_must_be_increasing(config):
    broken = copy.deepcopy(config)
    broken["attributes"]["income"]["edges"] = [900000, 400000]
    with pytest.raises(RegistryError, match="increasing"):
        load_registry(broken)


def test_band_labels_must_match_edges(config):
    broken = copy.deepcopy(config)
    broken["attributes"]["income"]["labels"] = ["low", "high"]
    with pytest.raises(RegistryError, match="len\\(labels\\)"):
        load_registry(broken)


def test_treatment_levels_must_exist(config):
    broken = copy.deepcopy(config)
    broken["attributes"]["pincode_group"]["treatment_levels"] = ["P9"]
    with pytest.raises(RegistryError, match="treatment_levels"):
        load_registry(broken)


def test_missing_attributes_is_an_error(config):
    broken = copy.deepcopy(config)
    broken.pop("attributes")
    with pytest.raises(RegistryError, match="attributes"):
        load_registry(broken)
