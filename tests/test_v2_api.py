"""R1 API contract tests: jobs, SSE, reports, decisions, certificates."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from auditor.pipeline import run_audit
from config_loader import load_config
from schemas import AgentEvent, AuditReport, ProbeEvent
from api.app import create_app


def _config(tmp_path):
    config = load_config()
    config["service"]["audit_db"] = str(tmp_path / "audits.db")
    config["service"]["sse_poll_seconds"] = 0.01
    config["certificate"]["db_path"] = str(tmp_path / "certificates.db")
    return config


def _probe(
    index: int,
    approved: bool = True,
    *,
    b_running: int | None = None,
    c_running: int | None = None,
) -> ProbeEvent:
    b = index + 1 if b_running is None else b_running
    c = 0 if c_running is None else c_running
    return ProbeEvent(
        probe_id="single-gender-female",
        phase="single_attribute",
        pair_index=index,
        changed_field="gender",
        original={"id": f"o{index}", "gender": "male"},
        twin={"id": f"t{index}", "gender": "female"},
        original_approved=True,
        twin_approved=approved,
        b_running=b,
        c_running=c,
        n_running=index + 1,
        net_flip_rate_running=(b - c) / (index + 1),
        ci_low_running=0.5,
        ci_high_running=1.0,
    )


def _report(model_id: int, config: dict) -> AuditReport:
    return AuditReport(
        model_id=model_id,
        config=config,
        findings=[],
        narrative="No finding survived the Skeptic.",
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
    yield AgentEvent(agent="planner", message=f"Audit plan for {model_id}.")
    time.sleep(0.05)
    if probe_event_sink is not None:
        probe_event_sink([_probe(0), _probe(1, approved=False)])
        time.sleep(0.05)
        probe_event_sink([_probe(2, b_running=2, c_running=1)])
    yield AgentEvent(agent="planner", message="Audit complete.")
    return _report(int(model_id), config)


def _failing_audit(
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
    yield AgentEvent(agent="planner", message="Audit started.")
    raise RuntimeError("sandbox exploded")


async def _wait_for(client: httpx.AsyncClient, audit_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = await client.get(f"/audits/{audit_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        await asyncio.sleep(0.02)
    raise AssertionError("audit did not finish")


@pytest.fixture
async def client_factory(tmp_path):
    apps = []
    clients = []

    async def make(audit_fn=_fake_audit):
        app = create_app(
            config=_config(tmp_path), audit_fn=audit_fn
        )
        apps.append(app)
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test")
        clients.append((client, context))
        return app, client

    yield make
    for client, context in reversed(clients):
        await client.aclose()
        await context.__aexit__(None, None, None)


async def test_health_and_audit_lifecycle(client_factory):
    _, client = await client_factory()
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    created = await client.post(
        "/audits",
        json={
            "model_id": 2,
            "seed": 42,
            "include_mitigation": False,
            "include_narrative": False,
        },
    )
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued"
    assert body["events_url"].endswith("/events")

    record = await _wait_for(client, body["id"])
    assert record["status"] == "completed"
    assert record["model_id"] == 2
    assert record["seed"] == 42
    assert record["result"]["model_id"] == 2
    assert record["last_seq"] >= 5
    assert record["event_count"] == record["last_seq"]
    assert record["decision"] is None
    assert record["sequential"] is False


async def test_unknown_audit_and_invalid_model(client_factory):
    _, client = await client_factory()
    assert (await client.get("/audits/nope")).status_code == 404
    assert (await client.get("/audits/nope/events")).status_code == 404
    invalid = await client.post("/audits", json={"model_id": 8})
    assert invalid.status_code == 422


async def _read_sse(client: httpx.AsyncClient, url: str) -> list[dict]:
    frames: list[dict] = []
    event = None
    data: str | None = None
    async with client.stream("GET", url) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
            elif line == "" and event:
                frames.append({"event": event, "data": json.loads(data or "{}")})
                event = None
                data = None
    return frames


async def test_sse_streams_agent_and_probe_events(client_factory):
    _, client = await client_factory()
    created = await client.post(
        "/audits",
        json={"model_id": 2, "include_mitigation": False, "include_narrative": False},
    )
    audit_id = created.json()["id"]
    frames = await _read_sse(client, f"/audits/{audit_id}/events")

    names = [frame["event"] for frame in frames]
    assert names.count("agent") == 2
    assert names.count("probe") == 3
    assert names[-1] == "done"

    probes = [frame["data"] for frame in frames if frame["event"] == "probe"]
    assert probes[0]["kind"] == "probe"
    assert probes[0]["data"]["probe_id"] == "single-gender-female"
    assert probes[0]["data"]["original_approved"] is True
    assert probes[0]["data"]["twin_approved"] is True
    assert probes[-1]["data"]["b_running"] == 2
    assert probes[-1]["data"]["c_running"] == 1
    assert probes[-1]["data"]["n_running"] == 3
    assert probes[-1]["seq"] < frames[-1]["data"]["last_seq"] + 1

    done = frames[-1]["data"]
    assert done["status"] == "completed"
    assert done["error"] is None


async def test_decision_requires_named_approver_and_issues_certificate(client_factory):
    _, client = await client_factory()
    created = await client.post(
        "/audits",
        json={"model_id": 2, "include_mitigation": False, "include_narrative": False},
    )
    audit_id = created.json()["id"]
    await _wait_for(client, audit_id)

    empty = await client.post(
        f"/audits/{audit_id}/decision",
        json={"approver": "  ", "decision": "approve"},
    )
    assert empty.status_code == 422

    approved = await client.post(
        f"/audits/{audit_id}/decision",
        json={"approver": "Asha Auditor", "decision": "approve"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["certificate"]["index"] == 0
    assert body["certificate"]["payload"]["approver"] == "Asha Auditor"
    assert body["audit"]["decision"]["certificate_index"] == 0

    again = await client.post(
        f"/audits/{audit_id}/decision",
        json={"approver": "Other", "decision": "reject"},
    )
    assert again.status_code == 409


async def test_certificates_list_verify_and_tamper(client_factory):
    _, client = await client_factory()
    created = await client.post(
        "/audits",
        json={"model_id": 2, "include_mitigation": False, "include_narrative": False},
    )
    audit_id = created.json()["id"]
    await _wait_for(client, audit_id)
    await client.post(
        f"/audits/{audit_id}/decision",
        json={"approver": "Asha Auditor", "decision": "reject"},
    )

    listed = await client.get("/certificates")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    verified = await client.post("/certificates/verify")
    assert verified.status_code == 200
    assert verified.json() == {"verified": True, "first_broken": None, "records": 1}

    refused = await client.post(
        "/certificates/tamper-demo", json={"index": 0, "confirm": False}
    )
    assert refused.status_code == 400

    tampered = await client.post(
        "/certificates/tamper-demo",
        json={"index": 0, "confirm": True},
    )
    assert tampered.status_code == 200
    body = tampered.json()
    assert body["verification"]["verified"] is False
    assert body["verification"]["first_broken"] == 0
    assert body["after"]["payload"]["approver"] == "Tampered Demo Record"

    after = await client.post("/certificates/verify")
    assert after.json()["verified"] is False


async def test_failed_audit_is_reported_and_not_signable(client_factory):
    _, client = await client_factory(_failing_audit)
    created = await client.post("/audits", json={"model_id": 2})
    audit_id = created.json()["id"]
    record = await _wait_for(client, audit_id)
    assert record["status"] == "failed"
    assert "RuntimeError" in record["error"]
    assert record["result"] is None

    decision = await client.post(
        f"/audits/{audit_id}/decision",
        json={"approver": "Asha", "decision": "approve"},
    )
    assert decision.status_code == 409


def _capturing_audit(seen):
    def audit(
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
        seen.update(
            model_id=model_id,
            api_url=api_url,
            target=target,
            sequential=sequential,
        )
        yield AgentEvent(agent="planner", message="Capturing audit.")
        return _report(int(model_id), config)

    return audit


async def test_target_adapter_is_resolved_and_recorded(client_factory):
    seen: dict = {}
    _, client = await client_factory(_capturing_audit(seen))
    created = await client.post(
        "/audits",
        json={
            "model_id": 1,
            "target": "sandbox:2",
            "sequential": True,
            "include_mitigation": False,
            "include_narrative": False,
        },
    )
    assert created.status_code == 202
    audit_id = created.json()["id"]
    record = await _wait_for(client, audit_id)

    assert record["status"] == "completed"
    assert record["target"] == "sandbox:2"
    assert record["model_id"] == 2
    assert record["sequential"] is True
    assert seen["model_id"] == 2
    assert seen["sequential"] is True
    assert seen["target"].name == "sandbox-model-2"
    assert seen["api_url"] == seen["target"].base_url


async def test_invalid_target_is_rejected(client_factory):
    _, client = await client_factory()
    bad_scheme = await client.post(
        "/audits", json={"model_id": 2, "target": "sandbox:9"}
    )
    assert bad_scheme.status_code == 400
    outside = await client.post(
        "/audits", json={"model_id": 2, "target": "../outside.yaml"}
    )
    assert outside.status_code == 400
    missing = await client.post(
        "/audits", json={"model_id": 2, "target": "targets/missing.yaml"}
    )
    assert missing.status_code == 400
