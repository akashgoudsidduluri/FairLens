"""R2 target adapter tests: YAML mapping, auth, limits, and sandbox validation."""

from __future__ import annotations

import ast
import json

import httpx
import pytest

from config_loader import REPO_ROOT, load_config
from auditor.prober import Prober
from sandbox.api import app as sandbox_app
from sandbox.generator import generate_applicants
from targets import (
    HTTPTargetAdapter,
    ProbeCapExceeded,
    TargetError,
    build_target,
    load_sandbox_target,
)
from targets.mapping import MissingEnvironmentVariable


def _applicants(n: int = 2):
    applicants, _ = generate_applicants(n, seed=101)
    return applicants


def _spec(**overrides):
    spec = {
        "name": "custom-lender",
        "base_url": "https://lender.test",
        "auth": {
            "type": "header",
            "header_name": "X-API-Key",
            "token_env": "LENDER_KEY",
        },
        "request": {
            "method": "POST",
            "path": "/decide",
            "query": {"product": "loan"},
            "headers": {"Accept": "application/json"},
            "applicant_map": {
                "ref": "${applicant.id}",
                "income": "${applicant.income}",
                "credit": "${applicant.credit_score}",
            },
            "body": {"applicants": "${applicants}"},
        },
        "response": {
            "items": "$.results",
            "approved": "decision",
            "approved_true": ["APPROVE"],
            "score": "score",
        },
        "limits": {
            "probe_cap": 10,
            "rate_limit_per_second": 0,
            "max_retries": 0,
            "timeout_seconds": 5,
        },
    }
    spec.update(overrides)
    return spec


def _flat_response() -> dict:
    return {"items": "$", "approved": "approved", "score": "score"}


async def test_custom_adapter_maps_request_and_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"decision": "APPROVE", "score": 701.5},
                    {"decision": "DENY", "score": 402.0},
                ]
            },
        )

    adapter = HTTPTargetAdapter(
        _spec(),
        transport=httpx.MockTransport(handler),
        env={"LENDER_KEY": "secret-key"},
    )
    applicants = _applicants(2)
    responses = await adapter.score_batch(applicants)

    assert [r.approved for r in responses] == [True, False]
    assert [r.score for r in responses] == [701.5, 402.0]
    assert captured["url"] == "https://lender.test/decide?product=loan"
    assert captured["headers"]["x-api-key"] == "secret-key"
    assert captured["headers"]["accept"] == "application/json"
    body = captured["body"]
    assert list(body) == ["applicants"]
    assert body["applicants"][0]["ref"] == applicants[0].id
    assert body["applicants"][0]["income"] == applicants[0].income
    assert body["applicants"][0]["credit"] == applicants[0].credit_score
    assert not {"gender", "name", "pincode"} & set(body["applicants"][0])
    assert adapter.probes_used == 2


async def test_bearer_and_query_auth_from_env():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["api_key"] = request.url.params.get("api_key")
        return httpx.Response(200, json=[{"approved": True, "score": 600}])

    bearer_spec = _spec(
        auth={"type": "bearer", "token_env": "LENDER_KEY"},
        request={
            "method": "POST",
            "path": "/decide",
            "body": "${applicants}",
        },
        response=_flat_response(),
    )
    bearer = HTTPTargetAdapter(
        bearer_spec,
        transport=httpx.MockTransport(handler),
        env={"LENDER_KEY": "abc123"},
    )
    await bearer.score_batch(_applicants(1))
    assert seen["authorization"] == "Bearer abc123"

    query_spec = _spec(
        auth={"type": "query", "param": "api_key", "token_env": "LENDER_KEY"},
        request={
            "method": "POST",
            "path": "/decide",
            "body": "${applicants}",
        },
        response=_flat_response(),
    )
    query = HTTPTargetAdapter(
        query_spec,
        transport=httpx.MockTransport(handler),
        env={"LENDER_KEY": "abc123"},
    )
    await query.score_batch(_applicants(1))
    assert seen["api_key"] == "abc123"


async def test_missing_auth_env_is_a_clear_error():
    adapter = HTTPTargetAdapter(
        _spec(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
        env={},
    )
    with pytest.raises(TargetError, match="LENDER_KEY"):
        await adapter.score_batch(_applicants(1))


async def test_base_url_env_default():
    spec = _spec(base_url="${LENDER_URL:-https://default.test}")
    adapter = HTTPTargetAdapter(spec, env={})
    assert adapter.base_url == "https://default.test"
    adapter = HTTPTargetAdapter(spec, env={"LENDER_URL": "https://env.test"})
    assert adapter.base_url == "https://env.test"
    with pytest.raises(MissingEnvironmentVariable):
        HTTPTargetAdapter(_spec(base_url="${LENDER_URL}"), env={})


async def test_rate_limiter_spaces_requests(monkeypatch):
    adapter = HTTPTargetAdapter(_spec(), env={"LENDER_KEY": "secret"})
    adapter.rate_limit_per_second = 10.0
    clock = {"now": 1000.0}
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return clock["now"]

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("targets.http.time.monotonic", fake_monotonic)
    monkeypatch.setattr("targets.http.asyncio.sleep", fake_sleep)

    await adapter._throttle()
    assert sleeps == []
    clock["now"] += 0.02
    await adapter._throttle()
    assert len(sleeps) == 1
    assert abs(sleeps[0] - 0.08) < 1e-9


async def test_retries_use_exponential_backoff_and_recover():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=[{"approved": True, "score": 650}])

    spec = _spec(
        request={"method": "POST", "path": "/decide", "body": "${applicants}"},
        auth={"type": "none"},
        response=_flat_response(),
    )
    spec["limits"] = {
        "probe_cap": 10,
        "rate_limit_per_second": 0,
        "max_retries": 2,
        "backoff_seconds": 0.001,
        "timeout_seconds": 5,
    }
    adapter = HTTPTargetAdapter(spec, transport=httpx.MockTransport(handler), env={})
    responses = await adapter.score_batch(_applicants(1))
    assert len(calls) == 3
    assert responses[0].approved is True
    assert adapter.probes_used == 1


async def test_4xx_is_not_retried():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, text="bad request")

    spec = _spec(
        request={"method": "POST", "path": "/decide", "body": "${applicants}"},
        auth={"type": "none"},
    )
    spec["limits"] = {
        "probe_cap": 10,
        "rate_limit_per_second": 0,
        "max_retries": 3,
        "backoff_seconds": 0.001,
        "timeout_seconds": 5,
    }
    adapter = HTTPTargetAdapter(spec, transport=httpx.MockTransport(handler), env={})
    with pytest.raises(TargetError, match="HTTP 400"):
        await adapter.score_batch(_applicants(1))
    assert len(calls) == 1
    assert adapter.probes_used == 0


async def test_hard_probe_cap_blocks_before_network():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        body = json.loads(request.content)
        return httpx.Response(
            200, json=[{"approved": True, "score": 600} for _ in body]
        )

    spec = _spec(
        request={"method": "POST", "path": "/decide", "body": "${applicants}"},
        auth={"type": "none"},
        response=_flat_response(),
    )
    spec["limits"] = {
        "probe_cap": 2,
        "rate_limit_per_second": 0,
        "max_retries": 0,
        "timeout_seconds": 5,
    }
    adapter = HTTPTargetAdapter(spec, transport=httpx.MockTransport(handler), env={})
    with pytest.raises(ProbeCapExceeded):
        await adapter.score_batch(_applicants(3))
    assert calls == []
    assert adapter.probes_used == 0

    adapter.reset()
    adapter.probe_cap = 3
    await adapter.score_batch(_applicants(2))
    with pytest.raises(ProbeCapExceeded):
        await adapter.score_batch(_applicants(2))
    assert adapter.probes_used == 2


def test_build_target_rejects_paths_outside_the_repository():
    config = load_config()
    with pytest.raises(ValueError, match="inside the repository"):
        build_target("../outside.yaml", config)
    with pytest.raises(ValueError, match="invalid sandbox target"):
        build_target("sandbox:not-a-number", config)


def test_global_probe_cap_is_a_ceiling_not_a_floor():
    config = load_config()
    config["targets"]["probe_cap"] = 10
    assert build_target("sandbox:2", config).probe_cap == 10
    config["targets"]["probe_cap"] = 1_000_000
    assert build_target("sandbox:2", config).probe_cap == 100_000


@pytest.fixture(scope="module")
def sandbox_transport():
    return httpx.ASGITransport(app=sandbox_app)


@pytest.mark.parametrize("model_id", range(1, 16))
async def test_sandbox_adapters_validate_against_the_service(model_id, sandbox_transport):
    adapter = load_sandbox_target(model_id, transport=sandbox_transport, env={})
    assert adapter.name == f"sandbox-model-{model_id}"
    assert adapter.spec["request"]["query"]["model"] == model_id
    assert adapter.probe_cap == 100000

    health = await adapter.health()
    assert health["status"] == "ok"

    applicants = _applicants(3)
    responses = await adapter.score_batch(applicants)
    assert len(responses) == len(applicants)
    assert all(isinstance(r.approved, bool) for r in responses)
    assert all(isinstance(r.score, float) for r in responses)
    assert adapter.probes_used == 3


async def test_prober_uses_target_adapter_and_counts_probes(sandbox_transport):
    adapter = load_sandbox_target(2, transport=sandbox_transport, env={})
    prober = Prober("http://unused.test", load_config(), target=adapter)
    health = await prober.check_health()
    assert health["status"] == "ok"
    assert prober.api_url == adapter.base_url

    result = await prober.probe_attribute(
        model_id=2,
        attribute="gender",
        target_group="female",
        comparison_group="male",
        n=20,
        seed=42,
    )
    assert result.n == 20
    assert result.requested_n == 20
    assert result.stopped_early is False
    assert adapter.probes_used == 40


def test_run_audit_with_target_adapter_end_to_end(sandbox_transport):
    from auditor.pipeline import collect_audit

    config = load_config()
    config["data"]["n_observational"] = 4000
    config["audit"]["n_pairs"] = 12
    config["audit"]["min_pairs"] = 5
    config["audit"]["intersectional_pairs_per_cell"] = 6
    config["audit"]["min_cell_size"] = 3
    config["audit"]["matched_n_pairs"] = 6
    config["audit"]["bootstrap_iterations"] = 50

    target = load_sandbox_target(2, transport=sandbox_transport, env={})
    events, report = collect_audit(
        2,
        target.base_url,
        config,
        seed=42,
        include_mitigation=False,
        include_narrative=False,
        target=target,
    )
    assert report.model_id == 2
    assert len(report.findings) >= 3
    assert any(event.agent == "prober" for event in events)
    assert target.probes_used > 0


def test_targets_do_not_import_sandbox_scoring():
    violations: list[str] = []
    for path in (REPO_ROOT / "targets").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name in {"sandbox.models", "sandbox.api", "sandbox"}:
                    violations.append(f"{path.name}: {name}")
    assert not violations, violations
