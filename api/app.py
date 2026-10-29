"""FastAPI audit service for FairLens v2.

The service starts an audit, streams agent and probe events over SSE, exposes
the completed report, and gates certificates behind a named human decision.
Audit execution and storage are injected in tests through ``create_app``.
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, Header, HTTPException, Query, status
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
from api.catalog import build_catalog, check_endpoint
from api.evidence import build_evidence, results_directory
from api.replays import (
    export_replay,
    find_replay,
    list_replays,
    load_replay,
    replay_directory,
)
from api.schemas import (
    AuditCreateRequest,
    AuditCreated,
    AuditRecord,
    CertificateList,
    DecisionInfo,
    DecisionRequest,
    DecisionResponse,
    EndpointCheckRequest,
    EndpointCheckResponse,
    EvidenceReport,
    HealthResponse,
    ReplayFile,
    ReplayList,
    ReplaySummary,
    ServiceMeta,
    StreamEvent,
    TamperRequest,
    TamperResponse,
    TargetCatalog,
    VerifyResponse,
)
from api.storage import AuditStore, create_store
from targets import TargetError, build_target, sandbox_model_id
from targets.base import apply_probe_cap
from targets.http import HTTPTargetAdapter

HEARTBEAT_SECONDS = 15.0


def _audit_config(
    config: dict[str, Any], model_id: int, search: bool | None
) -> dict[str, Any]:
    """Return the config this audit runs with.

    Suite B models (8-15) default to the generalized search; every other target
    keeps the frozen single/intersectional protocol unless ``search=True`` is
    explicit. The shared service config is never mutated: a copy is made only
    when the flag has to change.
    """

    enabled = bool(
        ((config.get("audit") or {}).get("search") or {}).get("enabled", False)
    )
    wanted = search if search is not None else 8 <= model_id <= 15
    if not wanted or enabled:
        return config
    updated = copy.deepcopy(config)
    updated.setdefault("audit", {}).setdefault("search", {})["enabled"] = True
    return updated


def _sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(
        "data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )
    return "\n".join(lines) + "\n\n"


def _record_response(
    record: dict[str, Any], replay_dir: Any = None
) -> AuditRecord:
    decision = record.get("decision")
    replay_id = record.get("replay_id")
    if replay_id is None and replay_dir is not None and record.get("status") == "completed":
        match = find_replay(replay_dir, record)
        replay_id = match["id"] if match else None
    return AuditRecord(
        id=record["id"],
        status=record["status"],
        model_id=record.get("model_id"),
        target=record.get("target"),
        api_url=record["api_url"],
        seed=int(record["seed"]),
        include_mitigation=bool(record["include_mitigation"]),
        include_narrative=bool(record["include_narrative"]),
        sequential=bool(record.get("sequential", False)),
        probe_cap=(
            int(record["probe_cap"]) if record.get("probe_cap") is not None else None
        ),
        created_at=record["created_at"],
        started_at=record.get("started_at"),
        completed_at=record.get("completed_at"),
        error=record.get("error"),
        result=record.get("result"),
        event_count=int(record.get("event_count", 0)),
        last_seq=int(record.get("last_seq", 0)),
        decision=DecisionInfo(**decision) if decision else None,
        replay_id=replay_id,
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
    replay_dir: Any = None,
    export_replays: bool | None = None,
    evidence_dir: Any = None,
) -> FastAPI:
    cfg = config or load_config()
    audit_store = store or create_store(cfg)
    cert_db = repo_path(cfg["certificate"]["db_path"])
    replays_path = replay_dir or replay_directory(cfg)
    evidence_path = evidence_dir or results_directory(cfg)
    record_replays = (
        export_replays if export_replays is not None else replay_dir is not None
    )

    def record_replay(audit_id: str, report: dict[str, Any]) -> None:
        export_replay(audit_store, audit_id, replays_path, report=report)

    manager = AuditJobManager(
        audit_store,
        cfg,
        audit_fn=audit_fn,
        max_workers=int(cfg.get("service", {}).get("max_workers", 2)),
        on_complete=record_replay if record_replays else None,
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

    @app.get("/meta", response_model=ServiceMeta, tags=["service"])
    def meta() -> ServiceMeta:
        """Public config values used to label evidence in the UI."""

        audit = cfg.get("audit") or {}
        sequential = audit.get("sequential") or {}
        return ServiceMeta(
            materiality=float(audit.get("materiality", 0.02)),
            alpha=float(audit.get("alpha", 0.05)),
            ci_level=float(audit.get("ci_level", 0.95)),
            bootstrap_iterations=int(audit.get("bootstrap_iterations", 4000)),
            n_pairs=int(audit.get("n_pairs", 2000)),
            probe_cap=int((cfg.get("targets") or {}).get("probe_cap", 100000)),
            sequential_enabled=bool(sequential.get("enabled", False)),
            sequential_min_pairs=int(sequential.get("min_pairs", 1000)),
            sequential_check_every=int(sequential.get("check_every", 200)),
        )

    @app.get("/targets", response_model=TargetCatalog, tags=["targets"])
    def targets() -> TargetCatalog:
        """Model Library: the validation suite, real models, and the LLM target.

        Capabilities and availability are read from the server, so the browser
        cannot claim a target is available when it is not.
        """

        return build_catalog(cfg)

    @app.post(
        "/targets/check", response_model=EndpointCheckResponse, tags=["targets"]
    )
    def check_connected_endpoint(
        request: EndpointCheckRequest,
    ) -> EndpointCheckResponse:
        """Server-side health check for the connected-endpoint form."""

        return check_endpoint(request)

    @app.post(
        "/audits",
        response_model=AuditCreated,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["audits"],
    )
    def start_audit(request: AuditCreateRequest) -> AuditCreated:
        if request.model_id > 15:
            raise HTTPException(
                status_code=422, detail="model_id must be between 1 and 15"
            )
        model_id = request.model_id
        target_ref = (request.target or "").strip() or None
        adapter = None
        if request.target_spec is not None:
            if target_ref is not None:
                raise HTTPException(
                    status_code=422,
                    detail="target and target_spec are mutually exclusive",
                )
            if not isinstance(request.target_spec, dict):
                raise HTTPException(status_code=422, detail="target_spec must be an object")
            if request.target_spec.get("family"):
                raise HTTPException(
                    status_code=400,
                    detail="inline specs may not declare a family",
                )
            try:
                adapter = HTTPTargetAdapter(dict(request.target_spec))
                apply_probe_cap(adapter, (cfg.get("targets") or {}).get("probe_cap"))
            except (TargetError, ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid connected endpoint: {exc}",
                ) from exc
            api_url = adapter.base_url
            target_ref = f"inline:{adapter.name}"
        elif target_ref is not None:
            try:
                adapter = build_target(target_ref, cfg, base_url=request.api_url)
            except (TargetError, ValueError, FileNotFoundError) as exc:
                raise HTTPException(
                    status_code=400, detail=f"invalid target: {exc}"
                ) from exc
            api_url = adapter.base_url
            sandbox_model = sandbox_model_id(target_ref)
            if sandbox_model is not None:
                model_id = sandbox_model
        else:
            api_url = (request.api_url or str(cfg["api"]["base_url"])).strip()
        if not api_url:
            raise HTTPException(status_code=422, detail="api_url cannot be empty")
        global_probe_cap = (cfg.get("targets") or {}).get("probe_cap")
        effective_probe_cap = (
            int(adapter.probe_cap)
            if adapter is not None
            else (int(global_probe_cap) if global_probe_cap is not None else None)
        )
        seed = int(cfg.get("seed", 42) if request.seed is None else request.seed)
        sequential = (
            request.sequential
            if request.sequential is not None
            else bool(cfg.get("audit", {}).get("sequential", {}).get("enabled", False))
        )
        audit_id = uuid.uuid4().hex
        audit_store.create_audit(
            audit_id=audit_id,
            model_id=model_id,
            target=target_ref,
            api_url=api_url,
            seed=seed,
            include_mitigation=request.include_mitigation,
            include_narrative=request.include_narrative,
            sequential=sequential,
            probe_cap=effective_probe_cap,
        )
        manager.start(
            audit_id,
            model_id=model_id,
            api_url=api_url,
            seed=seed,
            include_mitigation=request.include_mitigation,
            include_narrative=request.include_narrative,
            sequential=sequential,
            target=adapter,
            config=_audit_config(cfg, model_id, request.search),
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
        return _record_response(record, replays_path)

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
    async def stream_events(
        audit_id: str,
        last_event_id: int | None = Query(
            default=None,
            ge=0,
            description="Resume after this sequence. The Last-Event-ID header also works.",
        ),
        last_event_id_header: str | None = Header(
            default=None, alias="Last-Event-ID"
        ),
    ) -> StreamingResponse:
        record = await asyncio.to_thread(audit_store.get_audit, audit_id)
        if record is None:
            raise HTTPException(status_code=404, detail="audit not found")

        resume_from = max(0, int(last_event_id or 0))
        if last_event_id_header:
            try:
                resume_from = max(resume_from, int(last_event_id_header))
            except ValueError:
                pass

        async def frames() -> AsyncIterator[str]:
            last_seq = resume_from
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
            audit=_record_response(updated, replays_path), certificate=certificate
        )

    @app.get("/replays", response_model=ReplayList, tags=["replays"])
    def replays() -> ReplayList:
        """Recently recorded audits, newest first. No target is contacted."""

        summaries = [
            ReplaySummary.model_validate(item)
            for item in list_replays(replays_path)
        ]
        summaries.sort(
            key=lambda item: item.recorded_at or item.id, reverse=True
        )
        return ReplayList(replays=summaries, count=len(summaries))

    @app.get(
        "/replays/{replay_id}", response_model=ReplayFile, tags=["replays"]
    )
    def get_replay(replay_id: str) -> ReplayFile:
        """The full event stream and report of one recorded audit."""

        payload = load_replay(replays_path, replay_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="replay not found")
        return ReplayFile.model_validate(payload)

    @app.get("/evidence", response_model=EvidenceReport, tags=["evidence"])
    def evidence() -> EvidenceReport:
        """Aggregates computed from the committed evaluation results."""

        return EvidenceReport(
            generated_at=datetime.now(timezone.utc),
            **build_evidence(evidence_path),
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


app = create_app(replay_dir=replay_directory())
