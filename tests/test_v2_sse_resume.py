"""SSE resume: a reconnect can continue after a sequence, via query or header."""

from __future__ import annotations

import asyncio
import json

import httpx

from api.app import create_app
from config_loader import load_config
from schemas import AgentEvent, AuditReport


def _config(tmp_path):
    config = load_config()
    config["service"]["audit_db"] = str(tmp_path / "audits.db")
    config["service"]["sse_poll_seconds"] = 0.01
    config["certificate"]["db_path"] = str(tmp_path / "certificates.db")
    return config


def _fake_audit(model_id, api_url, config, seed=None, **kwargs):
    for index in range(3):
        yield AgentEvent(agent="planner", message=f"step {index + 1}")
    return AuditReport(model_id=model_id, config=config, findings=[], narrative="done")


async def _client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _wait_completed(client, audit_id: str) -> None:
    for _ in range(200):
        record = (await client.get(f"/audits/{audit_id}")).json()
        if record["status"] in {"completed", "failed"}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("audit did not finish")


async def _read_frames(client, url: str, headers: dict[str, str] | None = None):
    frames: list[dict] = []
    event = None
    data: str | None = None
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
            elif line == "" and event:
                frames.append({"event": event, "data": data})
                event = None
                data = None
    return frames


async def _start(client) -> str:
    response = await client.post(
        "/audits",
        json={"model_id": 2, "include_mitigation": False, "include_narrative": False},
    )
    assert response.status_code == 202
    audit_id = response.json()["id"]
    await _wait_completed(client, audit_id)
    return audit_id


async def test_sse_resumes_from_query_sequence(tmp_path):
    app = create_app(config=_config(tmp_path), audit_fn=_fake_audit)
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            audit_id = await _start(client)
            frames = await _read_frames(
                client, f"/audits/{audit_id}/events?last_event_id=2"
            )
            agents = [frame for frame in frames if frame["event"] == "agent"]
            assert len(agents) == 1
            assert json.loads(agents[0]["data"])["seq"] == 3
            assert frames[-1]["event"] == "done"


async def test_sse_resumes_from_last_event_id_header(tmp_path):
    app = create_app(config=_config(tmp_path), audit_fn=_fake_audit)
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            audit_id = await _start(client)
            frames = await _read_frames(
                client,
                f"/audits/{audit_id}/events",
                headers={"Last-Event-ID": "2"},
            )
            agents = [frame for frame in frames if frame["event"] == "agent"]
            assert len(agents) == 1
            assert json.loads(agents[0]["data"])["seq"] == 3
