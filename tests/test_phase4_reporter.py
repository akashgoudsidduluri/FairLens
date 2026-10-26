from __future__ import annotations

import json

import pytest

from config_loader import load_config
from report import reporter
from report.number_check import allowed_numbers, check_numbers, extract_numbers
from report.reporter import build_payload, generate_narrative, template_narrative
from schemas import AuditReport, Evidence, Finding, ImpactEstimate


def _finding(status="kept"):
    return Finding(
        id="single-gender-female",
        kind="single_attribute",
        attribute_or_subgroup="gender=female",
        target_group="female",
        comparison_group="male",
        evidence=Evidence(
            n=2000,
            b=1307,
            c=0,
            net_flip_rate=0.6535,
            ci_low=0.633,
            ci_high=0.6735,
            p_raw=0.0,
            p_adjusted=0.0,
        ),
        observational_gap=0.6605,
        status=status,
        reason="Kept by the Skeptic.",
    )


def _report():
    finding = _finding()
    impact = ImpactEstimate(
        finding_id=finding.id,
        subgroup=finding.attribute_or_subgroup,
        net_flip_rate=0.6535,
        per_10k=6535.0,
        ci_low_per_10k=6330.0,
        ci_high_per_10k=6735.0,
        explanation="About 6535 people per 10,000.",
    )
    return AuditReport(
        model_id=2,
        config={
            "audit": {
                "alpha": 0.05,
                "materiality": 0.02,
                "correction": "holm",
                "ci_level": 0.95,
                "n_pairs": 2000,
                "matched_n_pairs": 1000,
            },
            "mitigation": {"max_accuracy_loss_default": 0.02},
            "models": {"penalty_gender": 120.0},
        },
        findings=[finding, _finding(status="rejected")],
        impact=[impact],
        mitigation_curve=[
            {
                "offset": 0,
                "fairness_gap": 0.35,
                "accuracy_loss": 0.0,
                "accuracy": 0.59,
            },
            {
                "offset": 80,
                "fairness_gap": 0.04,
                "accuracy_loss": -0.01,
                "accuracy": 0.60,
            },
        ],
    )


def test_number_check_accepts_rounding_percent_and_commas():
    payload = {"net": 0.0265, "per_10k": 265.0, "scale": 10000, "ci": 0.95, "n": 2000}
    text = "A net rate of 2.65% (about 3%), or 265 people per 10,000, with 95% confidence and 2000 pairs."
    result = check_numbers(text, payload)
    assert result["passed"], result["unknown"]
    assert result["numeric_tokens"] >= 5


def test_number_check_rejects_invented_number():
    payload = {"net": 0.0265, "n": 2000}
    result = check_numbers("The model rejects 1234567 people.", payload)
    assert result["passed"] is False
    assert "1234567" in result["unknown"]


def test_number_check_accepts_scientific_p_value():
    payload = {"p_adjusted": 1.8e-94}
    assert check_numbers("Adjusted p=1.8e-94.", payload)["passed"]


def test_extract_numbers_ignores_group_labels():
    tokens = extract_numbers("Group P2 and N3, model 2, age 45+, p=0.02.")
    assert "2" in tokens
    assert "P2" not in tokens
    assert "N3" not in tokens
    assert "0.02" in tokens


def test_template_passes_number_check_and_word_limit():
    report = _report()
    payload = build_payload(report)
    text = template_narrative(payload, 250)
    check = check_numbers(text, payload)
    assert check["passed"], check["unknown"]
    assert len(text.split()) <= 250
    assert "evidence of" in text
    assert "proof of" in text  # explicitly negated ("not proof of")


def test_build_payload_does_not_leak_planted_penalties():
    payload = build_payload(_report())
    blob = json.dumps(payload)
    assert "penalty_gender" not in blob
    assert "120" not in blob
    assert "approval_threshold" not in blob
    assert payload["summary"]["kept"] == 1


def test_generate_narrative_template_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    payload = build_payload(_report())
    result = generate_narrative(payload, load_config())
    assert result["source"] == "template"
    assert check_numbers(result["narrative"], payload)["passed"]


def test_generate_narrative_falls_back_when_llm_invents_number(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(
        reporter,
        "_call_anthropic",
        lambda payload, extra="": "The model is 987654321 times biased.",
    )
    payload = build_payload(_report())
    result = generate_narrative(payload, load_config())
    assert result["source"] == "template_fallback"
    assert "987654321" in result["error"]
    assert check_numbers(result["narrative"], payload)["passed"]


def test_generate_narrative_accepts_clean_llm_output(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    clean = (
        "FairLens kept one gender finding for female applicants. The net flip rate "
        "was 0.6535 and about 6535 people per 10,000. This is evidence of disparate "
        "treatment in a synthetic sandbox, not proof of intent. A human must approve."
    )
    monkeypatch.setattr(reporter, "_call_anthropic", lambda payload, extra="": clean)
    payload = build_payload(_report())
    result = generate_narrative(payload, load_config())
    assert result["source"] == "anthropic"
    assert result["narrative"] == clean
