"""Recorded audit replays.

Every completed audit is written to a small gzip file containing the full event
stream and the report. Replays are deliberately files, not database rows: they
can be committed to the repository and played back without a sandbox, a target
service, or the job runner. The API only serves the bytes.

File format (version 1)::

    {
      "version": 1,
      "id": "sandbox-2-seed-42",
      "label": "Validation model 2",
      "recorded_at": "2026-10-28T14:38:10+00:00",
      "source_audit_id": "<original audit id>",
      "audit": { ...AuditRecord with result... },
      "events": [{"seq": 1, "kind": "agent", "data": {...}}, ...]
    }

The hash-named export of the current audit is written next to the curated demo
replays. Curated files use a readable id so they survive in git and are easy to
find; their ``source_audit_id`` still points at the audit that produced them.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path
from typing import Any

from config_loader import repo_path

DEFAULT_REPLAY_DIR = "data/replays"
REPLAY_VERSION = 1
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_LABELS = {
    "targets/real/adult-income.yaml": "UCI Adult (gradient boosting)",
    "targets/real/uci-credit-default.yaml": "UCI credit default (logistic regression)",
}


def replay_directory(config: dict[str, Any] | None = None) -> Path:
    configured = ((config or {}).get("service") or {}).get("replay_dir")
    return repo_path(configured or DEFAULT_REPLAY_DIR)


def safe_replay_id(replay_id: str) -> bool:
    return bool(_SAFE_ID.match(replay_id)) and ".." not in replay_id


def _label_for(record: dict[str, Any]) -> str:
    target = str(record.get("target") or "")
    if target in _LABELS:
        return _LABELS[target]
    if target.startswith("sandbox:"):
        return f"Validation model {target.split(':', 1)[1]}"
    if record.get("model_id") is not None:
        return f"Audit model {record['model_id']}"
    return "Recorded audit"


def _path_for(directory: Path, replay_id: str) -> Path | None:
    if not safe_replay_id(replay_id):
        return None
    return directory / f"{replay_id}.json.gz"


_AUDIT_FIELDS = (
    "id",
    "status",
    "model_id",
    "target",
    "api_url",
    "seed",
    "include_mitigation",
    "include_narrative",
    "sequential",
    "probe_cap",
    "created_at",
    "started_at",
    "completed_at",
    "error",
    "result",
    "event_count",
    "last_seq",
    "decision",
)


def _audit_payload(record: dict[str, Any]) -> dict[str, Any]:
    """The public audit record, without storage-only columns.

    The report is part of the recording so the player can render it without
    asking the live service. Datetimes stay ``datetime`` objects here; JSON
    encoding happens in :func:`export_replay`.
    """

    return {key: record.get(key) for key in _AUDIT_FIELDS}


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def export_replay(
    store: Any,
    audit_id: str,
    directory: Path,
    *,
    replay_id: str | None = None,
    label: str | None = None,
    report: dict[str, Any] | None = None,
) -> Path | None:
    """Persist one completed audit as a replay file.

    Returns the written path, or ``None`` when the audit is not completed and no
    final report was supplied. The job manager passes the report explicitly so
    the recording is on disk *before* the audit is marked complete; a reader can
    therefore never see ``completed`` with a replay id that does not exist yet.
    Nothing here talks to a target; the event stream and report come from the
    audit store.
    """

    record = store.get_audit(audit_id)
    if record is None:
        return None
    if report is None:
        if record.get("status") != "completed":
            return None
        report = record.get("result")
    if report is None:
        return None

    replay_id = replay_id or audit_id
    path = _path_for(directory, replay_id)
    if path is None:
        raise ValueError(f"invalid replay id: {replay_id!r}")

    audit = _audit_payload(record)
    audit["status"] = "completed"
    audit["result"] = report
    audit["replay_id"] = None
    completed_at = audit.get("completed_at") or record.get("started_at")
    if completed_at is None:
        from datetime import datetime, timezone

        completed_at = datetime.now(timezone.utc)
        audit["completed_at"] = completed_at
    payload = {
        "version": REPLAY_VERSION,
        "id": replay_id,
        "label": label or _label_for(record),
        "recorded_at": completed_at,
        "source_audit_id": audit_id,
        "audit": audit,
        "events": store.list_events(audit_id),
    }
    text = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), default=str
    )
    _write_atomic(path, gzip.compress(text.encode("utf-8"), compresslevel=6))
    return path


def _read(directory: Path, replay_id: str) -> dict[str, Any] | None:
    path = _path_for(directory, replay_id)
    if path is None or not path.exists():
        return None
    try:
        raw = gzip.decompress(path.read_bytes())
        payload = json.loads(raw)
    except (OSError, EOFError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != REPLAY_VERSION:
        return None
    return payload


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    audit = payload.get("audit") or {}
    events = payload.get("events") or []
    probes = sum(1 for event in events if event.get("kind") == "probe")
    findings = len((audit.get("result") or {}).get("findings") or [])
    return {
        "id": payload["id"],
        "label": payload.get("label") or "Recorded audit",
        "target": audit.get("target"),
        "model_id": audit.get("model_id"),
        "seed": audit.get("seed"),
        "recorded_at": payload.get("recorded_at") or audit.get("completed_at"),
        "duration_ms": _duration_ms(events),
        "event_count": len(events),
        "probe_count": probes,
        "findings": findings,
        "source_audit_id": payload.get("source_audit_id"),
    }


def _duration_ms(events: list[dict[str, Any]]) -> int:
    """Recorded wall-clock duration from event timestamps, if present."""

    timestamps: list[str] = []
    for event in events:
        data = event.get("data")
        if isinstance(data, dict):
            stamp = data.get("timestamp")
            if isinstance(stamp, str):
                timestamps.append(stamp)
    if len(timestamps) < 2:
        return 0
    try:
        from datetime import datetime

        first = datetime.fromisoformat(timestamps[0])
        last = datetime.fromisoformat(timestamps[-1])
    except ValueError:
        return 0
    return max(0, int((last - first).total_seconds() * 1000))


def list_replays(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    summaries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json.gz")):
        payload = _read(directory, path.name.removesuffix(".json.gz"))
        if payload is None:
            continue
        summaries.append(_summary(payload))
    return summaries


def load_replay(directory: Path, replay_id: str) -> dict[str, Any] | None:
    return _read(directory, replay_id)


def find_replay(
    directory: Path, record: dict[str, Any]
) -> dict[str, Any] | None:
    """Pick the recording that matches this audit.

    Exact audit id first, then the same target and seed, then the same target,
    and finally the same model id for legacy audits whose target was NULL.
    """

    candidates = list_replays(directory)
    if not candidates:
        return None

    def pick(predicate: Any) -> dict[str, Any] | None:
        matches = [item for item in candidates if predicate(item)]
        return matches[0] if matches else None

    audit_id = record.get("id")
    target = record.get("target")
    seed = record.get("seed")
    model_id = record.get("model_id")

    return (
        pick(lambda item: item.get("source_audit_id") == audit_id)
        or pick(
            lambda item: target is not None
            and item.get("target") == target
            and item.get("seed") == seed
        )
        or pick(
            lambda item: target is not None and item.get("target") == target
        )
        or pick(
            lambda item: target is None
            and model_id is not None
            and item.get("model_id") == model_id
        )
    )
