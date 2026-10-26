from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import schemas
from config_loader import load_config


def test_all_contracts_importable():
    expected = [
        "Applicant",
        "ModelResponse",
        "TwinPair",
        "Evidence",
        "Finding",
        "Check",
        "SkepticVerdict",
        "AgentEvent",
        "ImpactEstimate",
        "AuditReport",
        "CertificatePayload",
        "Certificate",
    ]
    for name in expected:
        assert hasattr(schemas, name), name


def test_applicant_roundtrip_and_validation():
    applicant = schemas.Applicant(
        id="A1",
        income=600000,
        loan_amount=400000,
        credit_score=710,
        employment_years=6,
        age=34,
        gender="female",
        pincode="500001",
        name="Asha Rao",
        pincode_group="P1",
        name_group="N1",
        urban_rural="urban",
        age_band="<35",
    )
    again = schemas.Applicant.model_validate_json(applicant.model_dump_json())
    assert again == applicant
    with pytest.raises(ValidationError):
        schemas.Applicant(**{**applicant.model_dump(), "credit_score": 901})
    with pytest.raises(ValidationError):
        schemas.Applicant(**{**applicant.model_dump(), "unexpected": 1})


def test_evidence_bounds():
    ev = schemas.Evidence(
        n=1000,
        b=40,
        c=5,
        net_flip_rate=0.035,
        ci_low=0.015,
        ci_high=0.055,
        p_raw=0.0001,
        p_adjusted=0.0003,
    )
    assert ev.net_flip_rate == pytest.approx(0.035)
    with pytest.raises(ValidationError):
        schemas.Evidence(**{**ev.model_dump(), "net_flip_rate": 1.5})


def test_canonical_json_is_stable_and_sorted():
    a = {"b": 1, "a": [2, 3], "nested": {"z": None, "y": True}}
    b = {"nested": {"y": True, "z": None}, "a": [2, 3], "b": 1}
    assert schemas.canonical_json(a) == schemas.canonical_json(b)
    assert schemas.canonical_json(a) == '{"a":[2,3],"b":1,"nested":{"y":true,"z":null}}'
    assert len(schemas.sha256_canonical(a)) == 64


def test_datetime_jsonable():
    now = datetime.now(timezone.utc)
    payload = schemas.to_jsonable({"when": now})
    assert payload["when"] == now.isoformat()


def test_frozen_preregistration_values():
    cfg = load_config()
    assert cfg["audit"]["alpha"] == 0.05
    assert cfg["audit"]["correction"] == "holm"
    assert cfg["audit"]["min_pairs"] == 1000
    assert cfg["audit"]["materiality"] == 0.02
    assert cfg["audit"]["min_cell_size"] == 200
    assert cfg["audit"]["n_pairs"] == 2000
    assert cfg["audit"]["seeds"] == [1, 2, 3, 4, 5]
    assert cfg["models"]["approval_threshold"] == 500.0
    assert cfg["models"]["penalty_gender"] == 120.0
    assert cfg["models"]["penalty_pincode"] == 120.0
    assert cfg["models"]["penalty_name"] == 120.0
    assert cfg["models"]["penalty_intersectional"] == 240.0
    assert cfg["data"]["synthetic_only"] is True


def test_expected_findings_frozen_before_audit():
    from pathlib import Path

    content = (Path(__file__).resolve().parents[1] / "expected_findings.md").read_text(
        encoding="utf-8"
    )
    assert "FROZEN before the first audit run" in content
    for model in range(1, 8):
        assert f"| {model} " in content
