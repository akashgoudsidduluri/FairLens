"""FastAPI audit service for FairLens v2.

The service starts an audit, streams agent and probe events over SSE, exposes
the completed report, and gates certificates behind a named human decision.
Audit execution and storage are injected in tests through ``create_app``.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse

from auditor.pipeline import run_audit
from config_loader import load_config, repo_path
from schemas import AuditReport, Certificate
from trust.certificate import (
    build_certificate_payload,
    init_db,
    issue,
    list_records,
    tamper_for_demo,
    verify,
)

from api.jobs import AuditJobManager
from api.schemas import (
    AuditCreateRequest,
    AuditCreated,
    AuditRecord,
    CertificateList,
    DecisionInfo,
    DecisionRequest,
    DecisionResponse,
    HealthResponse,
    StreamEvent,
    TamperRequest,
    TamperResponse,
    VerifyResponse,
)
from api.storage import AuditStore, create_store

HEARTBEAT_SECONDS = 15.0


def _sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(
        "data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )
    return "\n".join(lines) + "\n\n"


def _record_response(record: dict[str, Any]) -> AuditRecord:
    decision = record.get("decision")
    return AuditRecord(
        id=record["id"],
        status=record["status"],
        model_id=record.get("model_id"),
        target=record.get("target"),
        api_url=record["api_url"],
        seed=int(record["seed"]),
        include_mitigation=bool(record["include_mitigation"]),
        include_narrative=bool(record["include_narrative"]),
        created_at=record["created_at"],
        started_at=record.get("started_at"),
        completed_at=record.get("completed_at"),
        error=record.get("error"),
        result=record.get("result"),
        event_count=int(record.get("event_count", 0)),
        last_seq=int(record.get("last_seq", 0)),
        decision=DecisionInfo(**decision) if decision else None,
    )


def _verify_payload(cert_db: Any) -> VerifyResponse:
    ok, broken = verify(cert_db)
    return VerifyResponse(
        verified=ok,
        first_broken=broken,
        records=len(list_records(cert_db)),
    )


def create_app(
    *,
    config: dict[str, Any] | None = None,
    store: AuditStore | None = None,
    audit_fn: Callable[..., Any] = run_audit,
) -> FastAPI:
    cfg = config or load_config()
    audit_store = store or create_store(cfg)
    cert_db = repo_path(cfg["certificate"]["db_path"])
    manager = AuditJobManager(
        audit_store,
        cfg,
        audit_fn=audit_fn,
        max_workers=int(cfg.get("service", {}).get("max_workers", 2)),
    )
    poll_seconds = float(cfg.get("service", {}).get("sse_poll_seconds", 0.1))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        audit_store.init()
        init_db(cert_db)
        try:
            yield
        finally:
            manager.shutdown()

    app = FastAPI(
        title="FairLens Audit API",
        version="2.0.0",
        description=(
            "Start black-box fairness audits, stream agent and per-twin probe "
            "events, fetch number-checked reports, and issue human-approved "
            "tamper-evident certificates. Synthetic sandbox only."
        ),
        lifespan=lifespan,
    )
    app.state.config = cfg
    app.state.store = audit_store
    app.state.manager = manager
    app.state.cert_db = cert_db

    @app.get("/health", response_model=HealthResponse, tags=["service"])
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post(
        "/audits",
        response_model=AuditCreated,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["audits"],
    )
    def start_audit(request: AuditCreateRequest) -> AuditCreated:
        if request.model_id > 7:
            raise HTTPException(
                status_code=422, detail="model_id must be between 1 and 7"
            )
        api_url = (request.api_url or str(cfg["api"]["base_url"])).strip()
        if not api_url:
            raise HTTPException(status_code=422, detail="api_url cannot be empty")
        seed = int(cfg.get("seed", 42) if request.seed is None else request.seed)
        audit_id = uuid.uuid4().hex
        audit_store.create_audit(
            audit_id=audit_id,
            model_id=request.model_id,
            target=None,
            api_url=api_url,
            seed=seed,
            include_mitigation=request.include_mitigation,
            include_narrative=request.include_narrative,
        )
        manager.start(
            audit_id,
            model_id=request.model_id,
            api_url=api_url,
            seed=seed,
            include_mitigation=request.include_mitigation,
            include_narrative=request.include_narrative,
        )
        return AuditCreated(
            id=audit_id,
            events_url=f"/audits/{audit_id}/events",
            result_url=f"/audits/{audit_id}",
        )

    @app.get("/audits/{audit_id}", response_model=AuditRecord, tags=["audits"])
    def get_audit(audit_id: str) -> AuditRecord:
        record = audit_store.get_audit(audit_id)
        if record is None:
            raise HTTPException(status_code=404, detail="audit not found")
        return _record_response(record)

    @app.get(
        "/audits/{audit_id}/events",
        response_class=StreamingResponse,
        tags=["audits"],
        responses={
            200: {
                "model": StreamEvent,
                "content": {"text/event-stream": {}},
                "description": (
                    "SSE stream. Event names: agent, probe, done. Each frame has "
                    "an id equal to the monotonic audit event sequence; the data "
                    "line matches StreamEvent for agent/probe frames."
                ),
            }
        },
    )
    async def stream_events(audit_id: str) -> StreamingResponse:
        record = await asyncio.to_thread(audit_store.get_audit, audit_id)
        if record is None:
            raise HTTPException(status_code=404, detail="audit not found")

        async def frames() -> AsyncIterator[str]:
            last_seq = 0
            last_emit = time.monotonic()
            yield "retry: 1000\n\n"
            while True:
                events = await asyncio.to_thread(
                    audit_store.list_events, audit_id, last_seq
                )
                for event in events:
                    last_seq = int(event["seq"])
                    yield _sse(
                        str(event["kind"]),
                        {
                            "seq": last_seq,
                            "kind": event["kind"],
                            "data": event["data"],
                        },
                        event_id=last_seq,
                    )
                    last_emit = time.monotonic()
                current = await asyncio.to_thread(audit_store.get_audit, audit_id)
                if current is None:
                    break
                terminal = current["status"] in {"completed", "failed"}
                if terminal and last_seq >= int(current.get("last_seq", 0)):
                    yield _sse(
                        "done",
                        {
                            "audit_id": audit_id,
                            "status": current["status"],
                            "error": current.get("error"),
                            "last_seq": last_seq,
                        },
                    )
                    break
                if time.monotonic() - last_emit >= HEARTBEAT_SECONDS:
                    yield ": keep-alive\n\n"
                    last_emit = time.monotonic()
                await asyncio.sleep(poll_seconds)

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(
        "/audits/{audit_id}/decision",
        response_model=DecisionResponse,
        tags=["audits"],
    )
    def decide(audit_id: str, request: DecisionRequest) -> DecisionResponse:
        record = audit_store.get_audit(audit_id)
        if record is None:
            raise HTTPException(status_code=404, detail="audit not found")
        if record["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"audit is {record['status']}, not completed",
            )
        if record.get("decision") is not None:
            raise HTTPException(
                status_code=409, detail="audit already has a human decision"
            )
        if record.get("result") is None:
            raise HTTPException(status_code=409, detail="audit has no report")
        report = AuditReport.model_validate(record["result"])
        try:
            payload = build_certificate_payload(
                report, report.config, request.approver, request.decision
            )
            certificate = issue(
                payload, request.approver, request.decision, cert_db
            )
            audit_store.record_decision(
                audit_id,
                approver=request.approver,
                decision=request.decision,
                certificate_index=certificate.index,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated = audit_store.get_audit(audit_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="audit not found")
        return DecisionResponse(
            audit=_record_response(updated), certificate=certificate
        )

    @app.get(
        "/certificates", response_model=CertificateList, tags=["certificates"]
    )
    def certificates() -> CertificateList:
        records: list[Certificate] = list_records(cert_db)
        return CertificateList(records=records, count=len(records))

    @app.post(
        "/certificates/verify", response_model=VerifyResponse, tags=["certificates"]
    )
    def verify_certificates() -> VerifyResponse:
        return _verify_payload(cert_db)

    @app.post(
        "/certificates/tamper-demo",
        response_model=TamperResponse,
        tags=["certificates"],
    )
    def tamper_certificate(request: TamperRequest) -> TamperResponse:
        if not request.confirm:
            raise HTTPException(
                status_code=400,
                detail="confirm must be true; this endpoint corrupts a real record",
            )
        try:
            result = tamper_for_demo(
                request.index, cert_db, field=request.field
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return TamperResponse(
            index=int(result["index"]),
            field=str(result["field"]),
            before=result["before"],
            after=result["after"],
            verification=_verify_payload(cert_db),
        )

    return app


app = create_app()
