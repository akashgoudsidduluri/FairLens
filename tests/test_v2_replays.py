"""Offline replay tests: export, discovery, serving, and matching.

A replay must be playable from files alone. These tests deliberately serve a
recording through the API without ever calling the injected audit runner, which
is the same guarantee the browser relies on.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from api import replays
from api.app import create_app
from config_loader import load_config
from schemas import AgentEvent, AuditReport, ProbeEvent


def _config(tmp_path: Path) -> dict:
    config = load_config()
    config["service"]["audit_db"] = str(tmp_path / "audits.db")
    config["service"]["sse_poll_seconds"] = 0.01
    config["certificate"]["db_path"] = str(tmp_path / "certificates.db")
    return config


def _probe(index: int) -> ProbeEvent:
    return ProbeEvent(
        probe_id="single-gender-female",
        phase="single_attribute",
        pair_index=index,
        changed_field="gender",
        original={"id": f"o{index}", "gender": "male"},
        twin={"id": f"t{index}", "gender": "female"},
        original_approved=True,
        twin_approved=index == 1,
        b_running=1,
        c_running=0,
        n_running=index + 1,
        net_flip_rate_running=1.0 / (index + 1),
        ci_low_running=0.4,
        ci_high_running=1.0,
    )


def _fake_audit(
    model_id,
    api_url,
    config,
    seed=None,
    *,
    include_mitigation=True,
    include_narrative=True,
    probe_event_sink=None,
    target=None,
    sequential=None,
):
    yield AgentEvent(agent="planner", message="Audit plan.")
    if probe_event_sink is not None:
        probe_event_sink([_probe(0), _probe(1)])
    yield AgentEvent(agent="skeptic", message="No finding survived.")
    return AuditReport(
        model_id=int(model_id),
        config=config,
        findings=[],
        narrative="No finding survived the Skeptic.",
    )


async def _wait_for(client: httpx.AsyncClient, audit_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = await client.get(f"/audits/{audit_id}")
        if response.json()["status"] in {"completed", "failed"}:
            return response.json()
        import asyncio

        await asyncio.sleep(0.02)
    raise AssertionError("audit did not finish")


@pytest.fixture
async def replay_client(tmp_path):
    calls: list[str] = []

    def counting_audit(*args, **kwargs):
        calls.append("run")
        return (yield from _fake_audit(*args, **kwargs))

    replay_dir = tmp_path / "replays"
    app = create_app(
        config=_config(tmp_path),
        audit_fn=counting_audit,
        replay_dir=replay_dir,
    )
    context = app.router.lifespan_context(app)
    await context.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    try:
        yield client, calls, replay_dir
    finally:
        await client.aclose()
        await context.__aexit__(None, None, None)


async def test_completed_audit_is_recorded_and_served(replay_client):
    client, calls, replay_dir = replay_client
    created = await client.post(
        "/audits",
        json={
            "model_id": 2,
            "seed": 42,
            "target": "sandbox:2",
            "include_mitigation": False,
            "include_narrative": False,
        },
    )
    assert created.status_code == 202
    audit_id = created.json()["id"]
    record = await _wait_for(client, audit_id)
    assert record["status"] == "completed"
    assert record["replay_id"] == audit_id
    assert calls == ["run"]

    files = list(replay_dir.glob("*.json.gz"))
    assert [path.name for path in files] == [f"{audit_id}.json.gz"]

    listing = await client.get("/replays")
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    summary = body["replays"][0]
    assert summary["id"] == audit_id
    assert summary["source_audit_id"] == audit_id
    assert summary["probe_count"] == 2
    assert summary["event_count"] == 4
    assert summary["findings"] == 0

    served = await client.get(f"/replays/{audit_id}")
    assert served.status_code == 200
    payload = served.json()
    assert payload["audit"]["id"] == audit_id
    assert payload["audit"]["status"] == "completed"
    assert payload["audit"]["result"]["model_id"] == 2
    assert [frame["kind"] for frame in payload["events"]] == [
        "agent",
        "probe",
        "probe",
        "agent",
    ]
    # Serving a recording never starts another audit.
    assert calls == ["run"]


async def test_replay_endpoints_do_not_start_jobs(replay_client):
    client, calls, replay_dir = replay_client
    replay_dir.mkdir(parents=True, exist_ok=True)
    assert (await client.get("/replays")).json()["count"] == 0
    assert (await client.get("/replays/does-not-exist")).status_code == 404
    assert calls == []


async def test_unknown_and_unsafe_replay_ids_are_404(replay_client):
    client, _, _ = replay_client
    assert (await client.get("/replays/..%2F..%2Fetc%2Fpasswd")).status_code == 404
    assert (await client.get("/replays/%2E%2E")).status_code == 404


# ------------------------------------------------------------------ unit tests


def _record(
    audit_id: str,
    *,
    target: str | None,
    model_id: int = 2,
    seed: int = 42,
    report: bool = True,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": audit_id,
        "status": "completed",
        "model_id": model_id,
        "target": target,
        "api_url": "http://sandbox",
        "seed": seed,
        "include_mitigation": False,
        "include_narrative": False,
        "sequential": False,
        "probe_cap": 100000,
        "created_at": now,
        "started_at": now,
        "completed_at": now,
        "error": None,
        "result": (
            {
                "model_id": model_id,
                "config": {},
                "findings": [],
                "narrative": "",
            }
            if report
            else None
        ),
        "event_count": 2,
        "last_seq": 2,
        "decision": None,
    }


class _Store:
    def __init__(self, record: dict, events: list[dict] | None = None) -> None:
        self.record = record
        self.events = events or [
            {"seq": 1, "kind": "agent", "data": {"agent": "planner", "message": "hi"}},
            {"seq": 2, "kind": "probe", "data": _probe(0).model_dump(mode="json")},
        ]

    def get_audit(self, audit_id: str) -> dict | None:
        return self.record if audit_id == self.record["id"] else None

    def list_events(self, audit_id: str, after_seq: int = 0) -> list[dict]:
        return [event for event in self.events if event["seq"] > after_seq]


def test_safe_replay_ids():
    assert replays.safe_replay_id("sandbox-2-seed-42")
    assert replays.safe_replay_id("abc.json")
    assert not replays.safe_replay_id("../escape")
    assert not replays.safe_replay_id("a/b")
    assert not replays.safe_replay_id("")
    assert not replays.safe_replay_id(".hidden")


def test_export_requires_a_completed_report(tmp_path):
    running = _record("running", target="sandbox:2")
    running["status"] = "running"
    assert replays.export_replay(_Store(running), "running", tmp_path) is None

    empty = _record("empty", target="sandbox:2", report=False)
    assert replays.export_replay(_Store(empty), "empty", tmp_path) is None


def test_find_replay_prefers_exact_then_target_then_model(tmp_path):
    exact = _record("audit-exact", target="sandbox:2", seed=42)
    replays.export_replay(_Store(exact), "audit-exact", tmp_path, replay_id="exact")

    target_seed = _record("audit-seed", target="sandbox:3", seed=7)
    replays.export_replay(
        _Store(target_seed), "audit-seed", tmp_path, replay_id="target-seed"
    )

    legacy = _record("audit-legacy", target=None, model_id=7, seed=42)
    replays.export_replay(
        _Store(legacy), "audit-legacy", tmp_path, replay_id="legacy-model-7"
    )

    assert (
        replays.find_replay(tmp_path, {"id": "audit-exact", "target": "sandbox:2", "seed": 42})
        or {}
    )["id"] == "exact"

    # Same target, different audit id: fall back to the target+seed recording.
    assert replays.find_replay(
        tmp_path, {"id": "other", "target": "sandbox:3", "seed": 7}
    )["id"] == "target-seed"

    # Same target, different seed: the target recording still matches.
    assert replays.find_replay(
        tmp_path, {"id": "other", "target": "sandbox:3", "seed": 99}
    )["id"] == "target-seed"

    # Legacy audits stored with target NULL match on model id alone.
    assert replays.find_replay(
        tmp_path, {"id": "other", "target": None, "model_id": 7, "seed": 1}
    )["id"] == "legacy-model-7"

    assert replays.find_replay(
        tmp_path, {"id": "other", "target": "sandbox:5", "model_id": 5, "seed": 1}
    ) is None


def test_replay_summary_and_duration(tmp_path):
    record = _record("audit-duration", target="sandbox:2")
    events = [
        {
            "seq": 1,
            "kind": "agent",
            "data": {
                "agent": "planner",
                "message": "start",
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
        },
        {
            "seq": 2,
            "kind": "probe",
            "data": _probe(0).model_dump(mode="json"),
        },
        {
            "seq": 3,
            "kind": "agent",
            "data": {
                "agent": "skeptic",
                "message": "stop",
                "timestamp": "2026-01-01T00:00:12+00:00",
            },
        },
    ]
    replays.export_replay(
        _Store(record, events), "audit-duration", tmp_path, replay_id="duration"
    )
    summary = replays.list_replays(tmp_path)[0]
    assert summary["id"] == "duration"
    assert summary["label"] == "Validation model 2"
    assert summary["duration_ms"] == 12_000
    assert summary["event_count"] == 3
    assert summary["probe_count"] == 1
