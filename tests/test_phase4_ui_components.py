"""Pure renderer tests for the custom Streamlit design system."""

from __future__ import annotations

from types import SimpleNamespace

from schemas import Evidence, Finding
from ui import components


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
        status=status,  # type: ignore[arg-type]
        reason="Rejected: confounded by income." if status == "rejected" else "Kept.",
    )


def test_pipeline_strip_marks_active_and_done_steps():
    html = components.pipeline_strip(
        {"planner": "done", "prober": "active", "skeptic": "failed"}
    )
    assert "fl-pipe-step--done" in html
    assert "fl-pipe-step--active" in html
    assert 'aria-current="step"' in html
    assert "fl-pipe-step--failed" in html
    assert html.count("fl-pipe-step") >= 7


def test_log_feed_colours_skeptic_rejections_and_escapes_html():
    events = [
        SimpleNamespace(
            agent="planner", message="Audit plan prepared.", timestamp="2026-01-01T10:00:00"
        ),
        SimpleNamespace(
            agent="skeptic",
            message="REJECTED pincode group: confounded by <script>",
            timestamp="2026-01-01T10:00:01",
        ),
    ]
    html = components.log_feed(events)
    assert "fl-event--reject" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "planner" in html and "skeptic" in html


def test_log_feed_empty_and_running_states():
    assert "No audit yet" in components.log_feed([])
    assert "Connecting" in components.log_feed([], running=True)


def test_finding_card_stamps_rejected_findings():
    kept = components.finding_card(_finding("kept"))
    rejected = components.finding_card(_finding("rejected"))
    assert "fl-finding--kept" in kept
    assert "REJECTED" not in kept
    assert "fl-finding--rejected" in rejected
    assert "fl-stamp" in rejected
    assert "REJECTED" in rejected
    assert "+65.3%" in kept


def test_impact_counter_contains_count_up_script_and_target():
    html = components.impact_counter(6535.0, label="people per 10,000")
    assert "<script>" in html
    assert "6535" in html
    assert "requestAnimationFrame" in html
    assert "people per 10,000" in html


def test_chain_view_marks_broken_record_and_verify_badge():
    certificates = [
        SimpleNamespace(
            index=0,
            prev_hash="0" * 64,
            record_hash="a" * 64,
            payload={
                "model_id": 2,
                "approver": "Dr Test",
                "decision": "approve",
                "timestamp": "2026-01-01T10:00:00+00:00",
            },
        ),
        SimpleNamespace(
            index=1,
            prev_hash="a" * 64,
            record_hash="b" * 64,
            payload={
                "model_id": 5,
                "approver": "Dr Test",
                "decision": "reject",
                "timestamp": "2026-01-01T10:01:00+00:00",
            },
        ),
    ]
    html = components.chain_view(certificates, broken_index=1)
    assert "GENESIS" in html
    assert "is-broken" in html
    assert "HASH MISMATCH" in html
    assert "fl-badge--ok" in components.verify_badge(True)
    assert "CHAIN BROKEN" in components.verify_badge(False)
    assert "NOT CHECKED" in components.verify_badge(None)
