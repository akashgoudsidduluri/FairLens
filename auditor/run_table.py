"""Run the audit on all seven models and compare with expected_findings.md.

This is the Phase 2 honest smoke table. It does not retune anything. Run:

    .venv\\Scripts\\python -m auditor.run_table
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from auditor.pipeline import collect_audit
from config_loader import REPO_ROOT, load_config


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_api(port: int) -> subprocess.Popen:
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
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.2)
    process.terminate()
    raise RuntimeError("sandbox API did not start")


def expectation_check(model_id: int, findings) -> tuple[str, list[str]]:
    kept = [f for f in findings if f.status == "kept"]
    kept_ids = {f.id for f in kept}
    misses: list[str] = []

    def single(attr: str) -> str:
        return next(f.id for f in findings if f.id.startswith(f"single-{attr}"))

    if model_id == 1:
        if kept:
            misses.append(f"expected no kept findings, got {sorted(kept_ids)}")
    elif model_id == 2:
        if single("gender") not in kept_ids:
            misses.append("gender finding not kept")
        if single("pincode_group") in kept_ids:
            misses.append("pincode finding unexpectedly kept")
        if single("name_group") in kept_ids:
            misses.append("name finding unexpectedly kept")
    elif model_id == 3:
        if single("pincode_group") not in kept_ids:
            misses.append("pincode finding not kept")
        if single("gender") in kept_ids:
            misses.append("gender finding unexpectedly kept")
    elif model_id == 4:
        if single("name_group") not in kept_ids:
            misses.append("name finding not kept")
        if single("gender") in kept_ids:
            misses.append("gender finding unexpectedly kept")
    elif model_id == 5:
        hotspot = [
            f
            for f in kept
            if f.kind == "intersectional"
            and "female" in f.attribute_or_subgroup
            and "45+" in f.attribute_or_subgroup
            and "rural" in f.attribute_or_subgroup
        ]
        if not hotspot:
            misses.append("intersectional female/45+/rural hotspot not kept")
        if single("gender") in kept_ids:
            misses.append("single-attribute gender was kept (expected immaterial)")
        if single("pincode_group") in kept_ids or single("name_group") in kept_ids:
            misses.append("unexpected pincode/name kept")
    elif model_id == 6:
        if kept:
            misses.append(f"expected no kept findings, got {sorted(kept_ids)}")
    elif model_id == 7:
        if kept:
            misses.append(f"confounded model had kept findings: {sorted(kept_ids)}")
        if not any(f.observational_gap >= 0.02 for f in findings):
            misses.append("no material observational gap found")
        confounded = any(
            f.status == "rejected"
            and ("confound" in f.reason.lower() or "legitimate" in f.reason.lower())
            for f in findings
        )
        if not confounded:
            misses.append("no candidate rejected as confounded")

    verdict = "PASS" if not misses else "MISS"
    return verdict, misses


def main() -> int:
    config = load_config()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    process = start_api(port)
    rows = []
    try:
        for model_id in range(1, 8):
            started = time.time()
            _, report = collect_audit(
                model_id,
                url,
                config,
                seed=config["seed"],
                include_mitigation=False,
                include_narrative=False,
            )
            elapsed = time.time() - started
            status, misses = expectation_check(model_id, report.findings)
            kept = [f for f in report.findings if f.status == "kept"]
            rows.append((model_id, status, len(kept), elapsed, misses, report))
            print(
                f"model {model_id}: {status:4s} | kept={len(kept)} | "
                f"findings={len(report.findings)} | {elapsed:.1f}s"
            )
            for f in report.findings:
                print(
                    f"   {f.id:44s} {f.status:10s} net={f.evidence.net_flip_rate:+.4f} "
                    f"p_adj={f.evidence.p_adjusted:.2g} obs_gap={f.observational_gap:+.4f}"
                )
            for miss in misses:
                print(f"   MISS: {miss}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    lines = [
        "# Phase 2 audit table (honest, seed 42)",
        "",
        "| Model | Result | Kept | Findings | Runtime | Misses |",
        "|---|---|---|---|---|---|",
    ]
    for model_id, status, kept_n, elapsed, misses, _ in rows:
        lines.append(
            f"| {model_id} | {status} | {kept_n} | {len(rows[model_id-1][5].findings)} | "
            f"{elapsed:.1f}s | {'; '.join(misses) if misses else 'none'} |"
        )
    output = REPO_ROOT / "eval" / "results" / "phase2_audit_table.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
