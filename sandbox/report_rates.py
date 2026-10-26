"""Start the sandbox API and print approval rates for models 1-7.

Usage (from repo root):
    .venv\\Scripts\\python -m sandbox.report_rates

This is a sandbox smoke script, not an audit. It never computes fairness
findings; it only checks that each model produces plausible decision rates.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

from config_loader import REPO_ROOT, load_config
from sandbox.generator import generate_applicants


def wait_for_health(url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{url}/health", timeout=1.0)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.3)
    raise RuntimeError(f"API did not become healthy: {last_error}")


def main() -> int:
    config = load_config()
    port = 8011
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
        wait_for_health(url)
        applicants, _ = generate_applicants(4000, seed=config["seed"])
        rows = []
        with httpx.Client(timeout=30.0) as client:
            for model_id in range(1, 8):
                responses: list[dict] = []
                for start in range(0, len(applicants), 500):
                    chunk = applicants[start : start + 500]
                    r = client.post(
                        f"{url}/score_batch",
                        params={"model": model_id},
                        json=[a.model_dump() for a in chunk],
                    )
                    r.raise_for_status()
                    responses.extend(r.json())
                overall = sum(r["approved"] for r in responses) / len(responses)
                female = [
                    r["approved"]
                    for a, r in zip(applicants, responses)
                    if a.gender == "female"
                ]
                male = [
                    r["approved"]
                    for a, r in zip(applicants, responses)
                    if a.gender == "male"
                ]
                rows.append(
                    (
                        model_id,
                        overall,
                        sum(female) / len(female),
                        sum(male) / len(male),
                    )
                )
        print("model  overall  female   male   female-male")
        for model_id, overall, f, m in rows:
            print(f"{model_id:5d}  {overall:7.3f}  {f:7.3f}  {m:6.3f}  {f - m:+8.3f}")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
