from __future__ import annotations

import socket
import subprocess
import sys
import time

import httpx
import pytest

from auditor.pipeline import collect_audit
from auditor.prober import Prober, ProberError
from config_loader import REPO_ROOT, load_config, with_overrides


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def api_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "sandbox.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise RuntimeError("test sandbox did not start")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="module")
def test_config():
    return with_overrides(
        load_config(),
        {
            "data.n_observational": 1200,
            "audit.n_pairs": 1000,
            "audit.intersectional_pairs_per_cell": 200,
            "audit.matched_n_pairs": 1000,
            "audit.bootstrap_iterations": 1000,
        },
    )


def test_pipeline_model2_keeps_gender_and_retains_rejections(api_url, test_config):
    events, report = collect_audit(
        2,
        api_url,
        test_config,
        seed=42,
        include_mitigation=False,
        include_narrative=False,
    )
    assert report.model_id == 2
    gender = next(f for f in report.findings if f.id.startswith("single-gender"))
    assert gender.status == "kept"
    assert gender.evidence.net_flip_rate > 0.2
    assert gender.matched_evidence is not None
    assert len(report.findings) >= 8
    assert any(f.status in {"rejected", "immaterial"} for f in report.findings)
    assert any(event.agent == "skeptic" for event in events)
    assert any(event.agent == "planner" for event in events)
    assert report.impact and report.impact[0].per_10k > 0


def test_pipeline_is_deterministic_for_same_seed(api_url, test_config):
    _, first = collect_audit(
        2, api_url, test_config, seed=7, include_mitigation=False, include_narrative=False
    )
    _, second = collect_audit(
        2, api_url, test_config, seed=7, include_mitigation=False, include_narrative=False
    )
    first_sig = [(f.id, f.status, f.evidence.b, f.evidence.c) for f in first.findings]
    second_sig = [(f.id, f.status, f.evidence.b, f.evidence.c) for f in second.findings]
    assert first_sig == second_sig


def test_unreachable_api_raises_friendly_error():
    cfg = with_overrides(load_config(), {"api.retries": 0, "api.timeout_seconds": 1})
    prober = Prober("http://127.0.0.1:1", cfg)
    with pytest.raises(ProberError, match="unreachable|Could not reach"):
        prober.check_health_sync()


def test_invalid_url_raises():
    with pytest.raises(ProberError):
        Prober("   ", load_config())
