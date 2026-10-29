"""Record the R5 Arena replays (Models 8, 9, 12, and Adult Income with age).

Run from the repository root:

    .venv\\Scripts\\python -m eval.record_replays

Each entry is a real audit with the documented settings: suite B models run the
generalized treatment x context search, and the Adult Income target is audited
with the generalized protocol so its age twins are part of the recording. The
files land in ``data/replays`` with readable ids and are played back by the
Arena without a sandbox, a target service, or a job runner.

The replay payload is written by :func:`api.replays.export_replay`, so the
recorded events and audit record have exactly the shape the API serves. The
script only supplies the store view and the readable id/label.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.replays import export_replay, replay_directory
from auditor.pipeline import run_audit
from config_loader import load_config
from eval.sandbox_runner import start_real_server, start_servers, stop_servers
from schemas import AuditReport, ProbeEvent
from targets import build_target

RECORDINGS: tuple[dict[str, Any], ...] = (
    {
        "replay_id": "sandbox-8-seed-42",
        "label": "Validation model 8 · suite B (age × context)",
        "model_id": 8,
        "target": "sandbox:8",
        "seed": 42,
    },
    {
        "replay_id": "sandbox-9-seed-42",
        "label": "Validation model 9 · suite B (region × context)",
        "model_id": 9,
        "target": "sandbox:9",
        "seed": 42,
    },
    {
        "replay_id": "sandbox-12-seed-42",
        "label": "Validation model 12 · suite B (name × context)",
        "model_id": 12,
        "target": "sandbox:12",
        "seed": 42,
    },
    {
        "replay_id": "adult-income-age-seed-42",
        "label": "UCI Adult · age treatment",
        "model_id": 2,
        "target": "targets/real/adult-income.yaml",
        "seed": 42,
    },
)


class _RecordedStore:
    """The two store reads ``export_replay`` needs, from one finished audit."""

    def __init__(self, record: dict[str, Any], events: list[dict[str, Any]]) -> None:
        self.record = record
        self.events = events

    def get_audit(self, audit_id: str) -> dict[str, Any] | None:
        return self.record if audit_id == self.record["id"] else None

    def list_events(self, audit_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        return [event for event in self.events if event["seq"] > after_seq]


def _search_config(config: dict[str, Any]) -> dict[str, Any]:
    """The shared config with the generalized search switched on."""

    updated = {**config, "audit": {**config["audit"]}}
    updated["audit"]["search"] = {**config["audit"]["search"], "enabled": True}
    return updated


def _target_env(reference: str, sandbox_url: str, real_url: str) -> dict[str, str]:
    """Point the YAML at the live server this recording started."""

    if reference.startswith("sandbox:"):
        return {"FAIRLENS_API_URL": sandbox_url}
    return {"FAIRLENS_REAL_URL": real_url}


def _run(
    task: dict[str, Any],
    config: dict[str, Any],
    api_url: str,
    sandbox_url: str,
    real_url: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one audit, keeping the same event order the API store would see."""

    model_id = int(task["model_id"])
    is_sandbox = str(task["target"]).startswith("sandbox:")
    target = build_target(
        str(task["target"]),
        config,
        env=_target_env(str(task["target"]), sandbox_url, real_url),
    )
    log: list[tuple[str, dict[str, Any]]] = []

    def sink(batch: list[ProbeEvent]) -> None:
        for event in batch:
            log.append(("probe", event.model_dump(mode="json")))

    started_at = datetime.now(timezone.utc)
    generator = run_audit(
        model_id,
        api_url,
        config,
        int(task["seed"]),
        include_mitigation=False,
        include_narrative=False,
        probe_event_sink=sink,
        target=target,
    )
    while True:
        try:
            event = next(generator)
        except StopIteration as stop:
            report: AuditReport = stop.value
            break
        log.append(("agent", event.model_dump(mode="json")))
    completed_at = datetime.now(timezone.utc)
    elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)

    events = [
        {"seq": index, "kind": kind, "data": data}
        for index, (kind, data) in enumerate(log, 1)
    ]
    report_json = report.model_dump(mode="json")
    record = {
        "id": f"recording-{task['replay_id']}",
        "status": "completed",
        "model_id": model_id,
        "target": task["target"],
        "api_url": api_url if is_sandbox else "",
        "seed": int(task["seed"]),
        "include_mitigation": False,
        "include_narrative": False,
        "sequential": False,
        "probe_cap": target.probe_cap,
        "created_at": started_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "error": None,
        "result": report_json,
        "event_count": len(events),
        "last_seq": len(events),
        "decision": None,
        "elapsed_ms": elapsed_ms,
    }
    return record, events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated replay ids to record; default is every recording",
    )
    parser.add_argument(
        "--directory",
        default="",
        help="Replay directory; defaults to the configured data/replays",
    )
    args = parser.parse_args(argv)

    config = _search_config(load_config())
    wanted = {value.strip() for value in args.only.split(",") if value.strip()}
    tasks = [
        task for task in RECORDINGS if not wanted or task["replay_id"] in wanted
    ]
    if wanted:
        unknown = wanted - {task["replay_id"] for task in RECORDINGS}
        if unknown:
            raise SystemExit(f"unknown replay ids: {', '.join(sorted(unknown))}")
    if not tasks:
        raise SystemExit("no recordings selected")

    directory = Path(args.directory) if args.directory else replay_directory(config)
    processes, urls = start_servers(1)
    sandbox_url = urls[0]
    real_url = ""
    needs_real = any(not task["target"].startswith("sandbox:") for task in tasks)
    failed = 0
    try:
        if needs_real:
            real_process, real_url = start_real_server()
            processes.append(real_process)
        for task in tasks:
            started = time.perf_counter()
            is_sandbox = str(task["target"]).startswith("sandbox:")
            try:
                record, events = _run(
                    task,
                    config,
                    sandbox_url if is_sandbox else real_url,
                    sandbox_url,
                    real_url,
                )
                store = _RecordedStore(record, events)
                path = export_replay(
                    store,
                    record["id"],
                    directory,
                    replay_id=task["replay_id"],
                    label=task["label"],
                    report=record["result"],
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"{task['replay_id']}: FAILED {type(exc).__name__}: {exc}")
                continue
            probes = sum(1 for event in events if event["kind"] == "probe")
            kept = sum(
                1
                for finding in record["result"]["findings"]
                if finding["status"] == "kept"
            )
            print(
                f"{task['replay_id']}: {probes:,} probe events, {kept} kept, "
                f"{time.perf_counter() - started:.1f}s -> {path}"
            )
    finally:
        stop_servers(processes)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
