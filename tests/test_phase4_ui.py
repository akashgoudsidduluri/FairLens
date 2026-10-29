"""Headless Streamlit tests for the Phase 4 audit and sign-off flow.

The audit itself is replaced with a tiny deterministic report so the UI test is
fast and does not depend on a running sandbox. The certificate database is
redirected to a temporary file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from config_loader import load_config
from schemas import AgentEvent, AuditReport, Evidence, Finding, ImpactEstimate
from trust.certificate import list_records, verify

ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path) -> dict:
    config = load_config()
    config["certificate"]["db_path"] = str(tmp_path / "ui-certificates.db")
    return config


def _finding(status: str = "kept") -> Finding:
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
        observational_rates={"female": 0.1, "male": 0.75},
        status=status,
        reason="Kept: all checks passed." if status == "kept" else "Rejected: confounded.",
    )


def _report(config: dict) -> AuditReport:
    finding = _finding()
    cells = []
    for gender in ("female", "male"):
        for age in ("<35", "35-44", "45+"):
            for urban in ("urban", "rural"):
                cells.append(
                    {
                        "target_gender": gender,
                        "age_band": age,
                        "urban_rural": urban,
                        "n": 500,
                        "b": 20 if gender == "female" else 2,
                        "c": 1,
                        "net_flip_rate": 0.038 if gender == "female" else 0.002,
                        "p_adjusted": 0.01 if gender == "female" else 0.9,
                    }
                )
    return AuditReport(
        model_id=2,
        config=config,
        findings=[finding, _finding(status="rejected")],
        impact=[
            ImpactEstimate(
                finding_id=finding.id,
                subgroup="gender=female",
                net_flip_rate=0.6535,
                per_10k=6535.0,
                ci_low_per_10k=6330.0,
                ci_high_per_10k=6735.0,
                explanation="About 6535 people per 10,000.",
            )
        ],
        mitigation_curve=[
            {
                "offset": 0,
                "segment_approval_rate": 0.10,
                "comparison_approval_rate": 0.75,
                "fairness_gap": 0.65,
                "signed_gap": 0.65,
                "accuracy": 0.61,
                "accuracy_loss": 0.0,
                "segment_n": 1000,
                "comparison_n": 2000,
                "base_accuracy": 0.61,
                "sampling": "natural population",
                "segment_share": 0.5,
            },
            {
                "offset": 80,
                "segment_approval_rate": 0.70,
                "comparison_approval_rate": 0.75,
                "fairness_gap": 0.05,
                "signed_gap": 0.05,
                "accuracy": 0.63,
                "accuracy_loss": -0.02,
                "segment_n": 1000,
                "comparison_n": 2000,
                "base_accuracy": 0.61,
                "sampling": "natural population",
                "segment_share": 0.5,
            },
        ],
        narrative=(
            "FairLens audited model 2 through its API. The Skeptic kept 1 of 2 "
            "candidate findings. This is evidence of disparate treatment in a "
            "synthetic sandbox, not proof of intent. A named human auditor must "
            "approve before any Audit Record is issued."
        ),
        number_check_result={
            "passed": True,
            "unknown": [],
            "checked": ["2", "1"],
            "numeric_tokens": 2,
            "allowed_count": 20,
            "source": "template",
        },
        observational={"intersectional_cells": cells, "rates": {}, "gaps": {}},
    )


@pytest.fixture
def app_test(monkeypatch, tmp_path):
    config = _config(tmp_path)
    report = _report(config)
    monkeypatch.setattr("config_loader.load_config", lambda *args, **kwargs: config)

    def fake_run_audit(model_id, api_url, config, seed=None, **kwargs):
        yield AgentEvent(
            agent="planner", message=f"Audit plan prepared for model {model_id}."
        )
        yield AgentEvent(
            agent="statistician",
            message=f"Candidate evidence computed for model {model_id}.",
        )
        run_report = report.model_copy(deep=True)
        run_report.model_id = int(model_id)
        return run_report

    monkeypatch.setattr("auditor.pipeline.run_audit", fake_run_audit)
    at = AppTest.from_file(str(ROOT / "ui" / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, [exc.value for exc in at.exception]
    return at, Path(config["certificate"]["db_path"])


def _click(at: AppTest, label: str) -> None:
    next(button for button in at.button if button.label == label).click()


def test_ui_renders_initial_state(app_test):
    at, db_path = app_test
    assert at.tabs
    assert any("No audit yet" in markdown.value for markdown in at.markdown)
    assert any("No audit records yet" in markdown.value for markdown in at.markdown)
    assert any("NOT CHECKED" in markdown.value for markdown in at.markdown)
    assert verify(db_path) == (True, None)


def test_ui_full_audit_and_human_approval_flow(app_test):
    at, db_path = app_test
    at.selectbox[0].select(2)
    _click(at, "Start Audit")
    at.run()

    assert not at.exception, [exc.value for exc in at.exception]
    assert not at.error, [err.value for err in at.error]
    labels = {metric.label: metric.value for metric in at.metric}
    assert labels["Kept findings"] == "1"
    assert labels["Rejected"] == "1"
    assert "NUMBER CHECK PASSED" in " ".join(markdown.value for markdown in at.markdown)
    assert any("audited model 2" in block.value for block in at.markdown)

    # An Audit Record cannot be issued without a named human.
    _click(at, "Approve & issue Audit Record")
    at.run()
    assert any("Enter the approver" in error.value for error in at.error)
    assert list_records(db_path) == []

    next(t for t in at.text_input if t.label == "Approver name").set_value("Dr Test Auditor")
    _click(at, "Approve & issue Audit Record")
    at.run()

    assert not at.exception, [exc.value for exc in at.exception]
    assert any("Audit Record #0 issued for Model 2" in msg.value for msg in at.success)
    records = list_records(db_path)
    assert len(records) == 1
    assert records[0].payload["decision"] == "approve"
    assert records[0].payload["approver"] == "Dr Test Auditor"
    assert verify(db_path) == (True, None)
    assert "NOT CHECKED" in " ".join(markdown.value for markdown in at.markdown)

    _click(at, "Verify chain")
    at.run()
    assert any("Chain verified" in msg.value for msg in at.success)
    assert "CHAIN VERIFIED" in " ".join(markdown.value for markdown in at.markdown)


def test_ui_demo_mode_runs_the_three_models(app_test):
    at, _ = app_test
    _click(at, "Demo mode")
    at.run()

    assert not at.exception, [exc.value for exc in at.exception]
    assert not at.error, [err.value for err in at.error]
    html = " ".join(markdown.value for markdown in at.markdown)
    assert "Demo run" in html
    assert "Model 2" in html and "Model 7" in html and "Model 5" in html
    assert "Audit of Model 5" in html
    assert len([select for select in at.selectbox if select.label == "Inspect a demo result"]) == 1


def test_ui_open_demo_result_restores_that_models_log(app_test):
    at, _ = app_test
    _click(at, "Demo mode")
    at.run()
    assert not at.exception, [exc.value for exc in at.exception]

    demo_events = at.session_state["demo_events"]
    assert set(demo_events) == {2, 7, 5}

    next(
        select for select in at.selectbox if select.label == "Inspect a demo result"
    ).set_value(2)
    at.run()
    _click(at, "Open demo result")
    at.run()

    assert not at.exception, [exc.value for exc in at.exception]
    assert at.session_state["report"].model_id == 2
    assert at.session_state["events"] == demo_events[2]
    assert all(
        "model 2" in event.message.lower()
        for event in at.session_state["events"]
    )


def test_ui_reject_logs_decision_without_approval(app_test):
    at, db_path = app_test
    _click(at, "Start Audit")
    at.run()
    next(t for t in at.text_input if t.label == "Approver name").set_value(
        "Dr Test Auditor"
    )
    _click(at, "Reject & log decision")
    at.run()

    assert not at.exception, [exc.value for exc in at.exception]
    assert any("Rejection logged as Audit Record #0" in msg.value for msg in at.warning)
    records = list_records(db_path)
    assert len(records) == 1
    assert records[0].payload["decision"] == "reject"
    assert verify(db_path) == (True, None)


def test_ui_certificate_tamper_is_detected(app_test):
    at, db_path = app_test
    # Seed one record directly so this test stays focused on the certificate tab.
    from trust.certificate import build_certificate_payload, issue

    payload = build_certificate_payload(
        _report(_config(Path(db_path).parent)), _config(Path(db_path).parent), "Seed", "approve"
    )
    issue(payload, "Seed", "approve", db_path)
    at.run()
    assert not at.exception

    at.checkbox[0].check()
    at.run()
    _click(at, "Demo: tamper with the newest record")
    at.run()
    assert any("Tampered field" in warning.value for warning in at.warning)
    ok, broken = verify(db_path)
    assert ok is False
    assert broken == 0
