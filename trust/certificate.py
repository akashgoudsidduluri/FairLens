"""Tamper-evident certificate chain backed by SQLite.

Hash rule (exact):

    record_hash = sha256(prev_hash + canonical_json(payload))

where canonical JSON has sorted keys, fixed separators, and no whitespace. The
first record's prev_hash is 64 zeroes. Verification recomputes the entire chain
and reports the first broken record index.

Scope and honesty
-----------------
A hash chain proves that stored records were not modified after issuance and
that ordering is intact. It does NOT prove who issued a record: anyone who can
rewrite the whole chain can recompute it. Authorship requires a digital
signature (e.g. Ed25519) and key management, which is future work. The UI labels
this limitation.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config_loader import repo_path
from schemas import (
    AuditReport,
    Certificate,
    CertificatePayload,
    canonical_json,
    sha256_canonical,
    utc_now_iso,
)

GENESIS_HASH = "0" * 64
TABLE = "certificates"


def _resolve(db_path: str | Path) -> Path:
    return repo_path(db_path)


@contextmanager
def _connection(path: Path):
    """Commit/rollback and always close, including on Windows file locks."""

    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: str | Path) -> Path:
    path = _resolve(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                idx INTEGER PRIMARY KEY,
                prev_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    return path


def _hash(prev_hash: str, payload_text: str) -> str:
    import hashlib

    return hashlib.sha256((prev_hash + payload_text).encode("utf-8")).hexdigest()


def issue(
    payload: dict[str, Any] | CertificatePayload,
    approver: str,
    decision: str,
    db_path: str | Path,
    *,
    timestamp: str | None = None,
) -> Certificate:
    """Issue one certificate. Requires an explicit named human approver."""

    if not approver or not approver.strip():
        raise ValueError("An explicit approver name is required to issue a certificate.")
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    raw = payload.model_dump() if isinstance(payload, CertificatePayload) else dict(payload)
    required = {"model_id", "findings_hash", "report_hash", "config_hash"}
    missing = required - set(raw)
    if missing:
        raise ValueError(f"certificate payload missing fields: {sorted(missing)}")
    ts = timestamp or raw.get("timestamp") or utc_now_iso()
    cert_payload = CertificatePayload(
        version=int(raw.get("version", 1)),
        model_id=int(raw["model_id"]),
        findings_hash=str(raw["findings_hash"]),
        report_hash=str(raw["report_hash"]),
        config_hash=str(raw["config_hash"]),
        approver=approver.strip(),
        decision=decision,  # type: ignore[arg-type]
        timestamp=ts,
    )
    payload_text = canonical_json(cert_payload)

    path = init_db(db_path)
    with _connection(path) as conn:
        row = conn.execute(
            f"SELECT idx, record_hash FROM {TABLE} ORDER BY idx DESC LIMIT 1"
        ).fetchone()
        index = 0 if row is None else int(row[0]) + 1
        prev_hash = GENESIS_HASH if row is None else str(row[1])
        record_hash = _hash(prev_hash, payload_text)
        conn.execute(
            f"INSERT INTO {TABLE} (idx, prev_hash, record_hash, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (index, prev_hash, record_hash, payload_text, ts),
        )
        conn.commit()
    return Certificate(
        index=index,
        prev_hash=prev_hash,
        record_hash=record_hash,
        payload=json.loads(payload_text),
        created_at=datetime.fromisoformat(ts),
    )


def clear_records(db_path: str | Path) -> int:
    """Delete every certificate row and leave an empty, initialized store.

    Returns the number of records that were removed. Missing databases are
    created empty so a reset is safe before the first certificate is issued.
    """

    path = init_db(db_path)
    with _connection(path) as conn:
        removed = int(
            conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        )
        conn.execute(f"DELETE FROM {TABLE}")
        conn.commit()
    return removed


def list_records(db_path: str | Path) -> list[Certificate]:
    path = _resolve(db_path)
    if not path.exists():
        return []
    with _connection(path) as conn:
        try:
            rows = conn.execute(
                f"SELECT idx, prev_hash, record_hash, payload, created_at "
                f"FROM {TABLE} ORDER BY idx"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    records: list[Certificate] = []
    for idx, prev_hash, record_hash, payload_text, created_at in rows:
        records.append(
            Certificate(
                index=int(idx),
                prev_hash=str(prev_hash),
                record_hash=str(record_hash),
                payload=json.loads(payload_text),
                created_at=datetime.fromisoformat(str(created_at)),
            )
        )
    return records


def verify(db_path: str | Path) -> tuple[bool, int | None]:
    """Recompute the chain. Returns (ok, first_broken_index_or_None)."""

    path = _resolve(db_path)
    if not path.exists():
        return True, None
    with _connection(path) as conn:
        try:
            rows = conn.execute(
                f"SELECT idx, prev_hash, record_hash, payload, created_at "
                f"FROM {TABLE} ORDER BY idx"
            ).fetchall()
        except sqlite3.OperationalError:
            return True, None

    expected_prev = GENESIS_HASH
    for expected_index, (idx, prev_hash, record_hash, payload_text, created_at) in enumerate(
        rows
    ):
        if int(idx) != expected_index:
            return False, expected_index
        if str(prev_hash) != expected_prev:
            return False, expected_index
        if _hash(expected_prev, str(payload_text)) != str(record_hash):
            return False, expected_index
        try:
            payload_obj = json.loads(str(payload_text))
        except json.JSONDecodeError:
            return False, expected_index
        if str(payload_obj.get("timestamp")) != str(created_at):
            return False, expected_index
        expected_prev = str(record_hash)
    return True, None


def tamper_for_demo(
    index: int, db_path: str | Path, *, field: str = "payload"
) -> dict[str, Any]:
    """Deliberately modify a stored row without updating its hash.

    Used by the UI's clearly labelled demo button and by tests.
    """

    if field not in {"payload", "prev_hash", "record_hash", "created_at"}:
        raise ValueError("unsupported tamper field")
    path = _resolve(db_path)
    if not path.exists():
        raise ValueError("certificate database does not exist")
    with _connection(path) as conn:
        row = conn.execute(
            f"SELECT idx, prev_hash, record_hash, payload, created_at FROM {TABLE} WHERE idx = ?",
            (index,),
        ).fetchone()
        if row is None:
            raise ValueError(f"no certificate at index {index}")
        before = {
            "index": int(row[0]),
            "prev_hash": row[1],
            "record_hash": row[2],
            "payload": json.loads(row[3]),
            "created_at": row[4],
        }
        tampered_payload: dict[str, Any] | None = None
        if field == "payload":
            data = json.loads(row[3])
            data["approver"] = "Tampered Demo Record"
            data["decision"] = (
                "reject" if data.get("decision") == "approve" else "approve"
            )
            new_value = canonical_json(data)
            tampered_payload = data
        elif field == "prev_hash":
            new_value = "f" * 64
        elif field == "record_hash":
            new_value = "e" * 64
        else:
            new_value = "1999-01-01T00:00:00+00:00"
        conn.execute(
            f"UPDATE {TABLE} SET {field} = ? WHERE idx = ?", (new_value, index)
        )
        conn.commit()
    after = dict(before)
    after[field] = tampered_payload if tampered_payload is not None else new_value
    return {"before": before, "after": after, "field": field, "index": index}


def build_certificate_payload(
    report: AuditReport,
    config: dict[str, Any],
    approver: str,
    decision: str,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Hash the findings, report, and config for the certificate payload."""

    findings_payload = [f.model_dump(mode="json") for f in report.findings]
    report_payload = report.model_dump(mode="json")
    return CertificatePayload(
        version=1,
        model_id=report.model_id,
        findings_hash=sha256_canonical(findings_payload),
        report_hash=sha256_canonical(report_payload),
        config_hash=sha256_canonical(config),
        approver=approver.strip(),
        decision=decision,  # type: ignore[arg-type]
        timestamp=timestamp or utc_now_iso(),
    ).model_dump()


def fresh_demo_db(path: str | Path) -> Path:
    """Remove an old demo database so the demo starts clean."""

    resolved = _resolve(path)
    if resolved.exists():
        resolved.unlink()
    return init_db(resolved)
