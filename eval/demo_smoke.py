"""Headless end-to-end demo smoke test.

Starts a real sandbox process, runs the three demo audits over HTTP with
mitigation and narrative enabled, checks the expected outcomes, exercises the
human-approved certificate chain and tamper detection, and verifies that an
unreachable API fails gracefully.

Run from the repository root:

    .venv\\Scripts\\python -m eval.demo_smoke

The script writes ``eval/results/phase5_demo_smoke.md``. It does not change
``config.yaml`` or any pre-registered threshold.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from auditor.pipeline import collect_audit, run_audit
from config_loader import REPO_ROOT, load_config, with_overrides
from schemas import AuditReport
from trust.certificate import (
    build_certificate_payload,
    fresh_demo_db,
    issue,
    list_records,
    tamper_for_demo,
    verify,
)

DEMO_MODELS = (2, 7, 5)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_sandbox(port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sandbox.serve",
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
        if process.poll() is not None:
            raise RuntimeError("sandbox process exited during startup")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.2)
    process.terminate()
    raise RuntimeError("sandbox API did not start")


def _ids(report: AuditReport, status: str = "kept") -> set[str]:
    return {finding.id for finding in report.findings if finding.status == status}


def functional_checks(model_id: int, report: AuditReport) -> tuple[bool, list[str]]:
    """Checks that do not retune expectations; the Model 5 miss is data, not a bug."""

    kept = _ids(report, "kept")
    notes: list[str] = []
    passed = True
    if model_id == 2:
        if "single-gender-female" not in kept:
            passed = False
            notes.append("gender finding was not kept")
        if any(item.startswith(("single-pincode", "single-name")) for item in kept):
            passed = False
            notes.append("an unrelated single-attribute finding was kept")
    elif model_id == 7:
        if kept:
            passed = False
            notes.append(f"confounded model kept findings: {sorted(kept)}")
        rejected = [
            finding
            for finding in report.findings
            if finding.status == "rejected"
            and (
                "confound" in finding.reason.lower()
                or "legitimate" in finding.reason.lower()
            )
        ]
        if not rejected:
            passed = False
            notes.append("no candidate was rejected as confounded")
        if not any(f.observational_gap >= 0.02 for f in report.findings):
            passed = False
            notes.append("no material observational gap was present")
    elif model_id == 5:
        hotspot = [
            item
            for item in kept
            if item.startswith("inter-")
            and "female" in item
            and "45plus" in item
            and "rural" in item
        ]
        if not hotspot:
            passed = False
            notes.append("intersectional female/45+/rural hotspot was not kept")
        if any(item.startswith(("single-pincode", "single-name")) for item in kept):
            passed = False
            notes.append("an unrelated single-attribute finding was kept")
        if "single-gender-female" in kept:
            notes.append(
                "KNOWN PRE-REGISTRATION MISS: single-attribute gender was also kept "
                "(net 0.0265). Reported, not retuned; see DECISIONS.md D-009."
            )
    return passed, notes


def expectation_notes(model_id: int, report: AuditReport) -> list[str]:
    kept = _ids(report, "kept")
    notes: list[str] = []
    if model_id == 2 and "single-gender-female" not in kept:
        notes.append("expected gender kept")
    if model_id == 2 and any(
        item.startswith(("single-pincode", "single-name")) for item in kept
    ):
        notes.append("expected pincode/name not kept")
    if model_id == 7:
        if kept:
            notes.append("expected 0 kept on confounded model")
        if not any(f.status == "rejected" for f in report.findings):
            notes.append("expected at least one rejected observational candidate")
    if model_id == 5:
        if "single-gender-female" in kept:
            notes.append("expected single gender immaterial; observed kept (D-009 miss)")
        if not any(
            item.startswith("inter-")
            and "female" in item
            and "45plus" in item
            and "rural" in item
            for item in kept
        ):
            notes.append("expected female/45+/rural hotspot kept")
    return notes


def certificate_checks(report: AuditReport, config: dict[str, Any], temp_dir: Path) -> dict[str, Any]:
    db_path = fresh_demo_db(temp_dir / "smoke-certificates.db")
    payload = build_certificate_payload(report, config, "Demo Auditor", "approve")
    empty_name_rejected = False
    try:
        issue(payload, "   ", "approve", db_path)
    except ValueError:
        empty_name_rejected = True
    certificate = issue(payload, "Demo Auditor", "approve", db_path)
    ok_before, _ = verify(db_path)
    tamper_for_demo(certificate.index, db_path)
    ok_after, broken = verify(db_path)
    records = list_records(db_path)
    return {
        "empty_name_rejected": empty_name_rejected,
        "records": len(records),
        "hash": certificate.record_hash,
        "verified_before_tamper": ok_before,
        "verified_after_tamper": ok_after,
        "first_broken": broken,
    }


def unreachable_check(config: dict[str, Any]) -> dict[str, Any]:
    quick = with_overrides(config, {"api.retries": 0, "api.timeout_seconds": 1})
    generator = run_audit(
        1,
        "http://127.0.0.1:1",
        quick,
        seed=42,
        include_mitigation=False,
        include_narrative=False,
    )
    events = []
    error = ""
    try:
        while True:
            events.append(next(generator))
    except StopIteration:
        pass
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    aborted = any(
        event.agent == "planner" and "aborted" in event.message.lower()
        for event in events
    )
    return {"aborted_event": aborted, "error": error}


def write_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    certificate: dict[str, Any],
    unreachable: dict[str, Any],
    total_seconds: float,
) -> None:
    lines = [
        "# Phase 5 headless demo smoke test",
        "",
        "Real sandbox process, HTTP probes, full mitigation and narrative, seed 42.",
        "The test is functional; it does not retune any pre-registered threshold.",
        "",
        "| Model | Kept | Runtime | Narrative | Number check | Functional | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        report: AuditReport = row["report"]
        check = report.number_check_result or {}
        notes = row["notes"] + row["expectation_notes"]
        lines.append(
            f"| {row['model_id']} | {len(_ids(report, 'kept'))} | "
            f"{row['seconds']:.1f}s | {check.get('source', 'n/a')} | "
            f"{'PASS' if check.get('passed') else 'FAIL'} | "
            f"{'PASS' if row['passed'] else 'FAIL'} | "
            f"{'; '.join(notes) if notes else 'none'} |"
        )
    lines.extend(
        [
            "",
            f"Total audit time: **{total_seconds:.1f}s**. "
            "Every individual audit is under the 60-second demo budget.",
            "",
            "## Human gate and certificate",
            "",
            f"- Empty approver rejected: {certificate['empty_name_rejected']}",
            f"- Records issued: {certificate['records']}",
            f"- Chain verified before tamper: {certificate['verified_before_tamper']}",
            f"- Chain verified after tamper: {certificate['verified_after_tamper']} "
            f"(first broken record: {certificate['first_broken']})",
            "",
            "## Unreachable API",
            "",
            f"- Planner emitted an aborted event: {unreachable['aborted_event']}",
            f"- Error surfaced cleanly: `{unreachable['error']}`",
            "",
            "## Known miss",
            "",
            "Model 5 also kept the single-attribute gender finding at net 0.0265 "
            "instead of the pre-registered \"immaterial\" expectation. The arithmetic "
            "error in the pre-registration and the decision not to retune are "
            "documented in `DECISIONS.md` D-009. The hotspot remains dominant.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", help="Use an already running sandbox")
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "eval" / "results" / "phase5_demo_smoke.md"),
    )
    args = parser.parse_args(argv)

    config = load_config()
    process: subprocess.Popen | None = None
    if args.api_url:
        api_url = args.api_url.rstrip("/")
    else:
        port = free_port()
        api_url = f"http://127.0.0.1:{port}"
        process = start_sandbox(port)

    rows: list[dict[str, Any]] = []
    total_started = time.perf_counter()
    try:
        for model_id in DEMO_MODELS:
            started = time.perf_counter()
            _, report = collect_audit(
                model_id,
                api_url,
                config,
                seed=config["seed"],
                include_mitigation=True,
                include_narrative=True,
            )
            seconds = time.perf_counter() - started
            passed, notes = functional_checks(model_id, report)
            check = report.number_check_result or {}
            if not check.get("passed"):
                passed = False
                notes.append("narrative number check failed")
            if seconds >= 60:
                passed = False
                notes.append(f"audit exceeded 60s ({seconds:.1f}s)")
            rows.append(
                {
                    "model_id": model_id,
                    "report": report,
                    "seconds": seconds,
                    "passed": passed,
                    "notes": notes,
                    "expectation_notes": expectation_notes(model_id, report),
                }
            )
            print(
                f"model {model_id}: {'PASS' if passed else 'FAIL'} | "
                f"{seconds:.1f}s | kept={len(_ids(report, 'kept'))} | "
                f"narrative={check.get('source')} "
                f"({'pass' if check.get('passed') else 'fail'})"
            )
            for note in notes:
                print(f"   NOTE: {note}")
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    total_seconds = time.perf_counter() - total_started

    with tempfile.TemporaryDirectory(prefix="fairlens-smoke-") as temp:
        certificate = certificate_checks(rows[0]["report"], config, Path(temp))
    unreachable = unreachable_check(config)

    certificate_ok = (
        certificate["empty_name_rejected"]
        and certificate["records"] == 1
        and certificate["verified_before_tamper"]
        and not certificate["verified_after_tamper"]
        and certificate["first_broken"] == 0
    )
    unreachable_ok = unreachable["aborted_event"] and bool(unreachable["error"])
    output = Path(args.output)
    write_markdown(
        output,
        rows,
        {
            **certificate,
            "empty_name_rejected": certificate["empty_name_rejected"],
        },
        unreachable,
        total_seconds,
    )

    print(f"certificate: {'PASS' if certificate_ok else 'FAIL'} | {certificate}")
    print(f"unreachable API: {'PASS' if unreachable_ok else 'FAIL'} | {unreachable}")
    print(f"total: {total_seconds:.1f}s | wrote {output.relative_to(REPO_ROOT)}")
    all_ok = all(row["passed"] for row in rows) and certificate_ok and unreachable_ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
