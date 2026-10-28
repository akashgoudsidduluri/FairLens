from __future__ import annotations

import json
import sqlite3

import pytest

from schemas import canonical_json, sha256_canonical
from trust.certificate import (
    GENESIS_HASH,
    clear_records,
    fresh_demo_db,
    init_db,
    issue,
    list_records,
    tamper_for_demo,
    verify,
)
from trust.reset_demo_data import main as reset_main


def _payload(i: int = 0):
    return {
        "model_id": 2,
        "findings_hash": f"findings-{i}",
        "report_hash": f"report-{i}",
        "config_hash": "config-hash",
    }


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "certs.db"
    init_db(path)
    return path


def test_issue_three_and_verify(db):
    certs = [
        issue(_payload(i), "Asha Auditor", "approve", db, timestamp=f"2026-10-27T10:0{i}:00+00:00")
        for i in range(3)
    ]
    ok, broken = verify(db)
    assert ok is True and broken is None
    records = list_records(db)
    assert len(records) == 3
    assert [c.index for c in records] == [0, 1, 2]
    assert certs[0].prev_hash == GENESIS_HASH
    assert certs[1].prev_hash == certs[0].record_hash
    assert certs[2].prev_hash == certs[1].record_hash
    for cert in certs:
        expected = __import__("hashlib").sha256(
            (cert.prev_hash + canonical_json(cert.payload)).encode("utf-8")
        ).hexdigest()
        assert cert.record_hash == expected


def test_requires_named_approver_and_valid_decision(db):
    with pytest.raises(ValueError, match="approver"):
        issue(_payload(), "   ", "approve", db)
    with pytest.raises(ValueError, match="decision"):
        issue(_payload(), "Asha", "maybe", db)


def test_payload_hashes_are_independent(db):
    issue(_payload(1), "Asha", "approve", db)
    record = list_records(db)[0]
    assert record.payload["findings_hash"] == "findings-1"
    assert record.payload["approver"] == "Asha"
    assert record.payload["decision"] == "approve"
    assert record.payload["timestamp"] == record.created_at.isoformat()


@pytest.mark.parametrize(
    "field", ["payload", "prev_hash", "record_hash", "created_at"]
)
def test_any_tampered_byte_fails_at_right_record(db, field):
    for i in range(3):
        issue(_payload(i), f"Auditor {i}", "approve", db)
    tamper_for_demo(1, db, field=field)
    ok, broken = verify(db)
    assert ok is False
    assert broken == 1


def test_tampering_payload_directly_with_whitespace_fails(db):
    for i in range(3):
        issue(_payload(i), f"Auditor {i}", "approve", db)
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT payload FROM certificates WHERE idx = 2").fetchone()
        conn.execute(
            "UPDATE certificates SET payload = ? WHERE idx = 2", (row[0] + " ",)
        )
        conn.commit()
    ok, broken = verify(db)
    assert (ok, broken) == (False, 2)


def test_tampering_index_fails(db):
    for i in range(3):
        issue(_payload(i), f"Auditor {i}", "approve", db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE certificates SET idx = 99 WHERE idx = 1")
        conn.commit()
    ok, broken = verify(db)
    assert ok is False
    assert broken == 1


def test_reordering_rows_fails(db):
    for i in range(3):
        issue(_payload(i), f"Auditor {i}", "approve", db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE certificates SET idx = -1 WHERE idx = 1")
        conn.execute("UPDATE certificates SET idx = 1 WHERE idx = 2")
        conn.execute("UPDATE certificates SET idx = 2 WHERE idx = -1")
        conn.commit()
    ok, broken = verify(db)
    assert ok is False
    assert broken == 1


def test_tamper_demo_returns_before_after(db):
    issue(_payload(), "Asha", "approve", db)
    result = tamper_for_demo(0, db)
    assert result["before"]["payload"]["approver"] == "Asha"
    assert result["after"]["payload"]["approver"] == "Tampered Demo Record"
    assert verify(db)[0] is False


def test_empty_or_missing_db_verifies_true(tmp_path):
    missing = tmp_path / "missing.db"
    assert verify(missing) == (True, None)
    fresh_demo_db(missing)
    assert verify(missing) == (True, None)


def test_clear_records_empties_the_chain(db):
    for i in range(3):
        issue(_payload(i), f"Auditor {i}", "approve", db)

    assert clear_records(db) == 3
    assert list_records(db) == []
    assert verify(db) == (True, None)


def test_clear_records_creates_a_missing_store(tmp_path):
    missing = tmp_path / "not-yet-created.db"
    assert clear_records(missing) == 0
    assert missing.exists()
    assert list_records(missing) == []


def test_reset_script_reports_what_it_removed(db, capsys):
    issue(_payload(), "Asha", "approve", db)

    assert reset_main(["--db", str(db)]) == 0
    output = capsys.readouterr().out
    assert "Cleared 1 certificate record" in output
    assert "audit database was not touched" in output
    assert list_records(db) == []
