from __future__ import annotations

import socket
import subprocess
import sys
import time

import httpx
import pytest

from config_loader import REPO_ROOT, load_config, with_overrides
from impact.impact import impact_per_10k
from impact.mitigate import build_curve, recommend
from schemas import Evidence, Finding


def _finding(net=0.03, low=0.01, high=0.05):
    return Finding(
        id="f",
        kind="single_attribute",
        attribute_or_subgroup="gender=female",
        target_group="female",
        comparison_group="male",
        evidence=Evidence(
            n=2000,
            b=100,
            c=40,
            net_flip_rate=net,
            ci_low=low,
            ci_high=high,
            p_raw=1e-8,
            p_adjusted=1e-8,
        ),
        observational_gap=0.2,
        status="kept",
    )


def test_impact_formula_and_ci():
    impact = impact_per_10k(_finding())
    assert impact.per_10k == pytest.approx(300.0)
    assert impact.ci_low_per_10k == pytest.approx(100.0)
    assert impact.ci_high_per_10k == pytest.approx(500.0)
    assert "10,000" in impact.explanation or "10,000" in impact.explanation


def test_impact_clamps_negative_net_to_zero():
    impact = impact_per_10k(_finding(net=-0.02, low=-0.04, high=0.01))
    assert impact.per_10k == 0.0
    assert impact.ci_low_per_10k == 0.0


def test_recommend_respects_accuracy_budget():
    curve = [
        {"offset": 0, "fairness_gap": 0.30, "accuracy_loss": 0.0},
        {"offset": 20, "fairness_gap": 0.10, "accuracy_loss": 0.01},
        {"offset": 40, "fairness_gap": 0.01, "accuracy_loss": 0.03},
    ]
    rec = recommend(curve, 0.02)
    assert rec is not None
    assert rec["offset"] == 20
    rec2 = recommend(curve, 0.05)
    assert rec2 is not None and rec2["offset"] == 40
    assert recommend([], 0.02) is None


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
            raise RuntimeError("sandbox did not start")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def test_build_curve_for_gender(api_url):
    config = with_overrides(
        load_config(),
        {"mitigation.n_samples": 2000, "mitigation.offset_max": 240},
    )
    curve = build_curve(
        2, api_url, {"gender": "female"}, config, seed=123
    )
    assert len(curve) == 13
    assert curve[0]["offset"] == 0
    assert curve[0]["sampling"] == "natural population"
    assert -1.0 <= curve[-1]["accuracy_loss"] <= 1.0
    assert curve[0]["fairness_gap"] > curve[-1]["fairness_gap"]
    rec = recommend(curve, 0.05)
    assert rec is not None and rec["offset"] in [p["offset"] for p in curve]


def test_build_curve_stratifies_rare_intersectional_segment(api_url):
    config = with_overrides(
        load_config(),
        {"mitigation.n_samples": 1200, "mitigation.offset_max": 240},
    )
    segment = {"gender": "female", "age_band": "45+", "urban_rural": "rural"}
    curve = build_curve(5, api_url, segment, config, seed=321)
    assert curve[0]["sampling"].startswith("stratified")
    assert curve[0]["segment_n"] == 1000
    assert curve[0]["fairness_gap"] > curve[-1]["fairness_gap"]
