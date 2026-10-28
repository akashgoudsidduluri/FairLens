"""R4 Model Library: server-side catalog, availability, and endpoint checks."""

from __future__ import annotations

import asyncio
import sqlite3
import time

import httpx

from api.app import create_app
from api.catalog import build_catalog, check_endpoint
from api.schemas import EndpointCheckRequest
from api.storage import SQLiteAuditStore
from config_loader import load_config
from schemas import AgentEvent, AuditReport
from targets.http import HTTPTargetAdapter

INLINE_SPEC = {
    "name": "connected-lender",
    "base_url": "http://127.0.0.1:9999",
    "request": {
        "method": "POST",
        "path": "/score_batch",
        "body": "${applicants}",
    },
    "response": {"items": "$", "approved": "approved"},
    "limits": {"probe_cap": 5000},
}


def _config(tmp_path):
    config = load_config()
    config["service"]["audit_db"] = str(tmp_path / "audits.db")
    config["service"]["sse_poll_seconds"] = 0.01
    config["certificate"]["db_path"] = str(tmp_path / "certificates.db")
    return config


# --------------------------------------------------------------------- catalog


def test_catalog_has_seven_validation_models_two_real_and_one_llm():
    catalog = build_catalog(load_config(), environ={})
    assert len(catalog.targets) == 10
    validation = [card for card in catalog.targets if card.kind == "validation"]
    real = [card for card in catalog.targets if card.kind == "real"]
    llm = [card for card in catalog.targets if card.kind == "llm"]

    assert [card.target for card in validation] == [
        f"sandbox:{index}" for index in range(1, 8)
    ]
    assert all(card.supported_probes for card in validation)
    assert all(not card.unsupported_probes for card in validation)
    assert [card.target for card in real] == [
        "targets/real/uci-credit-default.yaml",
        "targets/real/adult-income.yaml",
    ]
    assert [card.model_id for card in real] == [1, 2]
    assert len(llm) == 1
    assert llm[0].target == "llm:screener"


def test_real_cards_report_unsupported_probes_from_target_yaml():
    catalog = build_catalog(load_config(), environ={})
    for card in (item for item in catalog.targets if item.kind == "real"):
        assert card.availability.status == "available"
        assert card.supported_probes == ["gender"]
        # The dataset has no name/region/urban column, so those probes must be
        # listed as unsupported with a reason rather than silently ignored.
        assert set(card.unsupported_probes) == {
            "pincode_group",
            "name_group",
            "intersectional",
        }
        assert all(card.unsupported_probes.values())


def test_llm_card_reports_true_availability_from_environment():
    config = load_config()
    unavailable = build_catalog(config, environ={}).targets[-1]
    assert unavailable.kind == "llm"
    assert unavailable.availability.status == "unavailable"
    assert "ANTHROPIC_MODEL" in unavailable.availability.reason
    assert "ANTHROPIC_API_KEY" in unavailable.availability.reason

    available = build_catalog(
        config,
        environ={"ANTHROPIC_MODEL": "claude-test", "ANTHROPIC_API_KEY": "sk-test"},
    ).targets[-1]
    assert available.availability.status == "available"
    assert available.availability.reason == ""
    assert "claude-test" in (available.metric or "")
    assert set(available.supported_probes) == {"name_group", "pincode_group"}
    assert set(available.unsupported_probes) == {"gender", "intersectional"}


# -------------------------------------------------------------- endpoint check


def test_endpoint_check_rejects_bad_urls_and_credentials_in_url():
    for url in ["ftp://example.test", "not a url"]:
        result = check_endpoint(EndpointCheckRequest(base_url=url), environ={})
        assert result.ok is False
        assert "http://" in result.detail or "URL" in result.detail

    embedded = check_endpoint(
        EndpointCheckRequest(base_url="https://user:pass@example.test"), environ={}
    )
    assert embedded.ok is False
    assert "env var" in embedded.detail


def test_endpoint_check_requires_the_named_secret_to_exist():
    result = check_endpoint(
        EndpointCheckRequest(
            base_url="https://example.test", auth_env_var="LENDER_TOKEN"
        ),
        environ={},
    )
    assert result.ok is False
    assert "LENDER_TOKEN" in result.detail
    assert "not set" in result.detail


def test_endpoint_check_reads_health_and_models_over_http():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json={"status": "ok", "models": ["credit", "adult"]})

    result = check_endpoint(
        EndpointCheckRequest(
            base_url="https://lender.test/",
            auth_env_var="LENDER_TOKEN",
            auth_header="X-API-Key",
        ),
        environ={"LENDER_TOKEN": "secret"},
        transport=httpx.MockTransport(handler),
    )
    assert result.ok is True
    assert result.status_code == 200
    assert result.models == ["credit", "adult"]
    assert result.latency_ms >= 0
    assert seen["url"] == "https://lender.test/health"
    assert seen["key"] == "secret"


def test_endpoint_check_reports_http_failure_without_leaking_the_secret():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    result = check_endpoint(
        EndpointCheckRequest(base_url="https://lender.test"),
        environ={},
        transport=httpx.MockTransport(handler),
    )
    assert result.ok is False
    assert result.status_code == 503
    assert "503" in result.detail


# ------------------------------------------------------------------- API routes


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
    return AuditReport(model_id=model_id, config=config, findings=[], narrative="done")


async def _wait_for(client: httpx.AsyncClient, audit_id: str) -> dict:
    deadline = time.time() + 5
    while time.time() < deadline:
        body = (await client.get(f"/audits/{audit_id}")).json()
        if body["status"] in {"completed", "failed"}:
            return body
        await asyncio.sleep(0.01)
    raise AssertionError("audit did not finish")


async def test_targets_route_serves_the_catalog(tmp_path):
    app = create_app(config=_config(tmp_path), audit_fn=_fake_audit)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/targets")
            assert response.status_code == 200
            body = response.json()
            assert len(body["targets"]) == 10
            assert body["targets"][-1]["kind"] == "llm"
            assert body["targets"][-1]["availability"]["status"] in {
                "available",
                "unavailable",
            }


async def test_meta_route_serves_thresholds_from_config(tmp_path):
    app = create_app(config=_config(tmp_path), audit_fn=_fake_audit)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/meta")
            assert response.status_code == 200
            body = response.json()
            assert body["materiality"] == 0.02
            assert body["alpha"] == 0.05
            assert body["ci_level"] == 0.95
            assert body["bootstrap_iterations"] == 4000
            assert body["sequential_min_pairs"] == 1000
            assert body["sequential_check_every"] == 200


async def test_inline_target_spec_starts_an_audit_with_an_http_adapter(tmp_path):
    captured: dict[str, object] = {}

    def capturing_audit(*args, **kwargs):
        captured.update(kwargs)
        return _fake_audit(*args, **kwargs)

    app = create_app(config=_config(tmp_path), audit_fn=capturing_audit)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/audits",
                json={
                    "model_id": 1,
                    "target_spec": INLINE_SPEC,
                    "include_mitigation": False,
                    "include_narrative": False,
                },
            )
            assert response.status_code == 202, response.text
            body = response.json()
            record = await _wait_for(client, body["id"])

    assert record["status"] == "completed"
    assert record["target"] == "inline:connected-lender"
    assert record["probe_cap"] == 5000
    assert isinstance(captured["target"], HTTPTargetAdapter)
    assert record["api_url"] == "http://127.0.0.1:9999"


async def test_inline_target_spec_rejects_family_and_mixed_targets(tmp_path):
    app = create_app(config=_config(tmp_path), audit_fn=_fake_audit)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            with_family = dict(INLINE_SPEC, family="sandbox")
            response = await client.post(
                "/audits", json={"model_id": 1, "target_spec": with_family}
            )
            assert response.status_code == 400
            assert "family" in response.json()["detail"]

            mixed = await client.post(
                "/audits",
                json={
                    "model_id": 1,
                    "target": "sandbox:1",
                    "target_spec": INLINE_SPEC,
                },
            )
            assert mixed.status_code == 422
            assert "mutually exclusive" in mixed.json()["detail"]


def test_http_adapter_can_be_built_from_the_inline_spec():
    adapter = HTTPTargetAdapter(dict(INLINE_SPEC))
    assert isinstance(adapter, HTTPTargetAdapter)
    assert adapter.probe_cap == 5000
    assert adapter.base_url == "http://127.0.0.1:9999"


def test_store_migrates_audits_written_before_probe_cap(tmp_path):
    db = tmp_path / "audits.db"
    store = SQLiteAuditStore(db)
    store.init()
    store.create_audit(
        audit_id="before",
        model_id=2,
        target="sandbox:2",
        api_url="http://127.0.0.1:8010",
        seed=42,
        include_mitigation=False,
        include_narrative=False,
        sequential=False,
        probe_cap=5000,
    )
    store.close()

    # Simulate an R2/R3 database that predates the probe_cap column.
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE audits DROP COLUMN probe_cap")

    migrated = SQLiteAuditStore(db)
    migrated.init()
    assert migrated.get_audit("before")["probe_cap"] is None

    migrated.create_audit(
        audit_id="after",
        model_id=2,
        target="sandbox:2",
        api_url="http://127.0.0.1:8010",
        seed=42,
        include_mitigation=False,
        include_narrative=False,
        sequential=False,
        probe_cap=5000,
    )
    assert migrated.get_audit("after")["probe_cap"] == 5000
