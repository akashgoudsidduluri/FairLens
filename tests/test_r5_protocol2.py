"""R5.1 protocol-2 artifacts stay separate from protocol 1."""

from __future__ import annotations

from eval import run_suite_b as suite


def _row() -> dict:
    return {
        "suite": "B",
        "model_id": 15,
        "seed": 1,
        "materiality": 0.02,
        "runtime_s": 64.2,
        "cells_examined": 110,
        "cells_tested": 110,
        "discovery_pairs": 26000,
        "confirmation_pairs": 0,
        "candidates": 0,
        "confirmed": 0,
        "kept": 0,
        "rejected": 0,
        "immaterial": 0,
        "merged": 0,
        "kept_ids": [],
        "expectation": "PASS",
        "misses": [],
        "notes": [],
        "false_alarm_before": 0,
        "false_alarm_after": 0,
        "mde_n200": 0.099,
        "mde_n1000": 0.044,
        "planned_applicants": 68000,
        "diagnostic_applicants": 0,
        "probe_cap": 100000,
        "dose_response": [],
        "error": "",
    }


def test_tagged_writers_write_protocol_two_files_only(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, "RESULTS", tmp_path)

    csv_path = suite._write_csv([_row()], "_r51")
    assert csv_path.name == "suite_b_r51.csv"
    assert csv_path.exists()
    assert not (tmp_path / "suite_b.csv").exists()

    markdown_path = suite._write_markdown(
        [_row()], [], 42, 4000, "2026-01-01T00:00:00+00:00", "_r51"
    )
    assert markdown_path.name == "suite_b_r51.md"
    text = markdown_path.read_text(encoding="utf-8")
    assert "R5.1 sibling-context merge" in text
    assert "Protocol 1 vs protocol 2" in text
    assert not (tmp_path / "suite_b.md").exists()
