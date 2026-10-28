"""Background audit jobs.

Audits are synchronous generators (they call ``asyncio.run`` inside the HTTP
prober), so a small thread pool is the simplest correct boundary. Each worker
persists events as it goes; SSE readers poll the store rather than sharing
in-process queues. That keeps streaming safe across threads and processes.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Generator

from auditor.pipeline import run_audit
from schemas import AgentEvent, AuditReport, ProbeEvent

from api.storage import AuditStore

logger = logging.getLogger(__name__)

AuditGenerator = Generator[AgentEvent, None, AuditReport]


class AuditJobManager:
    def __init__(
        self,
        store: AuditStore,
        config: dict[str, Any],
        *,
        audit_fn: Callable[..., AuditGenerator] = run_audit,
        max_workers: int = 2,
        on_complete: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self.store = store
        self.config = config
        self.audit_fn = audit_fn
        self.on_complete = on_complete
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="fairlens-audit",
        )

    def start(
        self,
        audit_id: str,
        *,
        model_id: int,
        api_url: str,
        seed: int,
        include_mitigation: bool,
        include_narrative: bool,
        sequential: bool,
        target: Any = None,
    ) -> None:
        self._executor.submit(
            self._run,
            audit_id,
            model_id,
            api_url,
            seed,
            include_mitigation,
            include_narrative,
            sequential,
            target,
        )

    def _run(
        self,
        audit_id: str,
        model_id: int,
        api_url: str,
        seed: int,
        include_mitigation: bool,
        include_narrative: bool,
        sequential: bool,
        target: Any,
    ) -> None:
        try:
            self.store.mark_running(audit_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("could not mark audit %s running", audit_id)
            return

        def sink(batch: list[ProbeEvent]) -> None:
            self.store.append_events(
                audit_id,
                [("probe", event.model_dump(mode="json")) for event in batch],
            )

        try:
            generator = self.audit_fn(
                model_id,
                api_url,
                self.config,
                seed,
                include_mitigation=include_mitigation,
                include_narrative=include_narrative,
                probe_event_sink=sink,
                target=target,
                sequential=sequential,
            )
            report: AuditReport | None = None
            while True:
                try:
                    event = next(generator)
                except StopIteration as stop:
                    report = stop.value
                    break
                self.store.append_events(
                    audit_id, [("agent", event.model_dump(mode="json"))]
                )
            if report is None:
                raise RuntimeError("audit generator returned no report")
            report_json = report.model_dump(mode="json")
            if self.on_complete is not None:
                try:
                    # Record first, then publish "completed": a reader must never
                    # observe a completed audit whose replay file is missing.
                    self.on_complete(audit_id, report_json)
                except Exception:  # noqa: BLE001
                    # A recording failure must never turn a finished audit into a
                    # failed one; the report is still persisted below.
                    logger.exception("could not record replay for %s", audit_id)
            self.store.complete_audit(audit_id, report_json)
        except Exception as exc:  # noqa: BLE001
            logger.exception("audit %s failed", audit_id)
            self.store.fail_audit(audit_id, f"{type(exc).__name__}: {exc}")

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)
