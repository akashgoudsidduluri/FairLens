"""Audit persistence behind a small, swappable interface.

``AuditStore`` is the boundary. ``SQLiteAuditStore`` is the reference
implementation used by the local service. A Postgres implementation only needs
to satisfy the same methods; no route or job code imports SQLite directly.

SQLite runs in WAL mode with a busy timeout because an audit worker writes
events while SSE readers poll in the event loop. Every method opens and closes
its own connection so Windows does not hold a file lock between calls.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol
from urllib.parse import urlparse

from config_loader import repo_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class AuditStore(Protocol):
    """Storage contract shared by SQLite and future Postgres adapters."""

    def init(self) -> None: ...

    def create_audit(
        self,
        *,
        audit_id: str,
        model_id: int | None,
        target: str | None,
        api_url: str,
        seed: int,
        include_mitigation: bool,
        include_narrative: bool,
        sequential: bool,
        probe_cap: int | None = None,
    ) -> None: ...

    def mark_running(self, audit_id: str) -> None: ...

    def append_events(
        self, audit_id: str, events: list[tuple[str, dict[str, Any]]]
    ) -> int: ...

    def complete_audit(self, audit_id: str, result: dict[str, Any]) -> None: ...

    def fail_audit(self, audit_id: str, error: str) -> None: ...

    def get_audit(self, audit_id: str) -> dict[str, Any] | None: ...

    def list_events(
        self, audit_id: str, after_seq: int = 0
    ) -> list[dict[str, Any]]: ...

    def record_decision(
        self,
        audit_id: str,
        *,
        approver: str,
        decision: str,
        certificate_index: int,
    ) -> None: ...

    def close(self) -> None: ...


class SQLiteAuditStore:
    def __init__(self, path: str | Path) -> None:
        self.path = repo_path(path)
        self._closed = False

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise RuntimeError("audit store is closed")
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    model_id INTEGER,
                    target TEXT,
                    api_url TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    include_mitigation INTEGER NOT NULL DEFAULT 1,
                    include_narrative INTEGER NOT NULL DEFAULT 1,
                    sequential INTEGER NOT NULL DEFAULT 0,
                    probe_cap INTEGER,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error TEXT,
                    result_json TEXT,
                    approver TEXT,
                    decision TEXT,
                    certificate_index INTEGER,
                    decided_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (audit_id, seq),
                    FOREIGN KEY (audit_id) REFERENCES audits(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS audit_events_audit_seq "
                "ON audit_events (audit_id, seq)"
            )
            # Add v2 R2 columns to databases created by R1.
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(audits)").fetchall()
            }
            if "sequential" not in columns:
                conn.execute(
                    "ALTER TABLE audits ADD COLUMN sequential INTEGER NOT NULL DEFAULT 0"
                )
            # R4: persist the effective probe cap so a reload can never show the
            # global cap for an audit that ran under a stricter inline cap.
            if "probe_cap" not in columns:
                conn.execute("ALTER TABLE audits ADD COLUMN probe_cap INTEGER")

    def create_audit(
        self,
        *,
        audit_id: str,
        model_id: int | None,
        target: str | None,
        api_url: str,
        seed: int,
        include_mitigation: bool,
        include_narrative: bool,
        sequential: bool,
        probe_cap: int | None = None,
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO audits (
                    id, status, model_id, target, api_url, seed,
                    include_mitigation, include_narrative, sequential, probe_cap,
                    created_at
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    model_id,
                    target,
                    api_url,
                    seed,
                    int(include_mitigation),
                    int(include_narrative),
                    int(sequential),
                    probe_cap,
                    utc_now(),
                ),
            )

    def mark_running(self, audit_id: str) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE audits SET status = 'running', started_at = ? "
                "WHERE id = ? AND status = 'queued'",
                (utc_now(), audit_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"audit not found or not queued: {audit_id}")

    def append_events(
        self, audit_id: str, events: list[tuple[str, dict[str, Any]]]
    ) -> int:
        if not events:
            return self._last_seq(audit_id)
        now = utc_now()
        with self._connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM audits WHERE id = ?", (audit_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(f"audit not found: {audit_id}")
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM audit_events WHERE audit_id = ?",
                (audit_id,),
            ).fetchone()
            seq = int(row[0])
            for kind, payload in events:
                seq += 1
                conn.execute(
                    """
                    INSERT INTO audit_events (audit_id, seq, kind, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        audit_id,
                        seq,
                        kind,
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        now,
                    ),
                )
        return seq

    def _last_seq(self, audit_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM audit_events WHERE audit_id = ?",
                (audit_id,),
            ).fetchone()
        return int(row[0])

    def complete_audit(self, audit_id: str, result: dict[str, Any]) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE audits SET status = 'completed', completed_at = ?, "
                "result_json = ?, error = NULL WHERE id = ?",
                (
                    utc_now(),
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    audit_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"audit not found: {audit_id}")

    def fail_audit(self, audit_id: str, error: str) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE audits SET status = 'failed', completed_at = ?, error = ? "
                "WHERE id = ?",
                (utc_now(), error[:4000], audit_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"audit not found: {audit_id}")

    def get_audit(self, audit_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT a.*,
                       (SELECT COUNT(*) FROM audit_events e WHERE e.audit_id = a.id)
                           AS event_count,
                       (SELECT COALESCE(MAX(seq), 0) FROM audit_events e
                           WHERE e.audit_id = a.id) AS last_seq
                FROM audits a WHERE a.id = ?
                """,
                (audit_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        result_json = data.pop("result_json", None)
        data["result"] = json.loads(result_json) if result_json else None
        data["include_mitigation"] = bool(data["include_mitigation"])
        data["include_narrative"] = bool(data["include_narrative"])
        data["sequential"] = bool(data.get("sequential", 0))
        for key in ("created_at", "started_at", "completed_at", "decided_at"):
            if data.get(key):
                data[key] = _iso(str(data[key]))
        decision = data.get("decision")
        if decision:
            data["decision"] = {
                "approver": data["approver"],
                "decision": decision,
                "certificate_index": data["certificate_index"],
                "decided_at": data["decided_at"],
            }
        else:
            data["decision"] = None
        for key in ("approver", "certificate_index"):
            data.pop(key, None)
        return data

    def list_events(
        self, audit_id: str, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT seq, kind, payload_json
                FROM audit_events
                WHERE audit_id = ? AND seq > ?
                ORDER BY seq
                """,
                (audit_id, after_seq),
            ).fetchall()
        return [
            {
                "seq": int(row["seq"]),
                "kind": row["kind"],
                "data": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def record_decision(
        self,
        audit_id: str,
        *,
        approver: str,
        decision: str,
        certificate_index: int,
    ) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE audits
                SET approver = ?, decision = ?, certificate_index = ?, decided_at = ?
                WHERE id = ? AND decision IS NULL AND status = 'completed'
                """,
                (approver, decision, certificate_index, utc_now(), audit_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"audit cannot be decided: {audit_id}")

    def close(self) -> None:
        self._closed = True


def create_store(config: dict[str, Any]) -> AuditStore:
    """Build the configured store.

    ``service.database_url`` may be a ``sqlite:///`` URL. Postgres is an
    extension point: implement ``AuditStore`` and return it here. The routes and
    job manager do not know which backend is in use.
    """

    url = str(config.get("service", {}).get("database_url", "")).strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in {"sqlite", ""}:
            raise ValueError(
                f"Unsupported audit store scheme {parsed.scheme!r}; "
                "implement AuditStore for Postgres and select it here."
            )
        path = url.removeprefix("sqlite:///").removeprefix("sqlite://")
        return SQLiteAuditStore(path)
    return SQLiteAuditStore(config["service"]["audit_db"])
