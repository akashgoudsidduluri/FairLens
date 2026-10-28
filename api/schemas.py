"""HTTP contracts for the FairLens v2 audit service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas import AgentEvent, AuditReport, Certificate, ProbeEvent


class ServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StreamEvent(ServiceModel):
    """The JSON body of one SSE ``data:`` line."""

    seq: int
    kind: Literal["agent", "probe"]
    data: AgentEvent | ProbeEvent


class AuditCreateRequest(ServiceModel):
    """Start an audit against a sandbox model or a YAML target adapter.

    ``target`` accepts ``sandbox:N`` for the seven validation adapters or a
    repository-relative path to a YAML adapter. When omitted, the audit talks
    directly to ``api_url`` exactly as in v1.
    """

    model_id: int = Field(ge=1, le=7, description="Report model label (1-7)")
    api_url: str | None = Field(
        default=None, description="Sandbox base URL; defaults to config.yaml"
    )
    target: str | None = Field(
        default=None,
        description="Target adapter: 'sandbox:N' or a YAML path under the repo",
    )
    seed: int | None = Field(default=None, ge=0)
    include_mitigation: bool = True
    include_narrative: bool = True
    sequential: bool | None = Field(
        default=None,
        description="Override audit.sequential.enabled for this audit",
    )
    target_spec: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Inline declarative adapter spec from the connected-endpoint form. "
            "Mutually exclusive with target/api_url."
        ),
    )


class AuditCreated(ServiceModel):
    id: str
    status: Literal["queued"] = "queued"
    events_url: str
    result_url: str


class DecisionRequest(ServiceModel):
    approver: str = Field(min_length=1, max_length=200)
    decision: Literal["approve", "reject"]

    @field_validator("approver")
    @classmethod
    def _named_human(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("An explicit approver name is required.")
        return cleaned


class DecisionInfo(ServiceModel):
    approver: str
    decision: Literal["approve", "reject"]
    certificate_index: int
    decided_at: datetime


class AuditRecord(ServiceModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    model_id: int | None = None
    target: str | None = None
    api_url: str
    seed: int
    include_mitigation: bool
    include_narrative: bool
    sequential: bool = False
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: AuditReport | None = None
    event_count: int = 0
    last_seq: int = 0
    decision: DecisionInfo | None = None


class DecisionResponse(ServiceModel):
    audit: AuditRecord
    certificate: Certificate


class CertificateList(ServiceModel):
    records: list[Certificate]
    count: int


class VerifyResponse(ServiceModel):
    verified: bool
    first_broken: int | None = None
    records: int


class TamperRequest(ServiceModel):
    index: int = Field(default=0, ge=0)
    field: Literal["payload", "prev_hash", "record_hash", "created_at"] = "payload"
    confirm: bool = Field(
        default=False,
        description="Must be true. The endpoint deliberately corrupts a record.",
    )


class TamperResponse(ServiceModel):
    index: int
    field: str
    before: dict[str, Any]
    after: dict[str, Any]
    verification: VerifyResponse


class HealthResponse(ServiceModel):
    status: Literal["ok"] = "ok"
    service: str = "fairlens-api"
    version: str = "2.0.0"


class TargetAvailability(ServiceModel):
    status: Literal["available", "unavailable", "configured"]
    reason: str = ""


class TargetCard(ServiceModel):
    """One target in the Model Library, with its real capabilities."""

    id: str
    label: str
    kind: Literal["validation", "real", "llm"]
    family: str
    target: str
    model_id: int
    description: str
    supported_probes: list[str]
    unsupported_probes: dict[str, str]
    availability: TargetAvailability
    planned_pairs: int
    probe_cap: int | None = None
    metric: str | None = None


class TargetCatalog(ServiceModel):
    targets: list[TargetCard]
    service: str = "fairlens-api"


class ServiceMeta(ServiceModel):
    """Public thresholds the UI needs to label evidence and sequential stops.

    Values come from ``config.yaml``. The UI never hardcodes a threshold.
    """

    materiality: float
    alpha: float
    ci_level: float
    bootstrap_iterations: int
    n_pairs: int
    probe_cap: int
    sequential_enabled: bool
    sequential_min_pairs: int
    sequential_check_every: int


class EndpointCheckRequest(ServiceModel):
    """Sanity check a connected endpoint before Start Audit is enabled."""

    base_url: str = Field(min_length=1, max_length=2000)
    health_path: str = Field(default="/health", max_length=200)
    auth_env_var: str | None = Field(default=None, max_length=100)
    auth_header: str = Field(default="X-API-Key", max_length=100)
    probe_cap: int = Field(default=100000, ge=0, le=10_000_000)


class EndpointCheckResponse(ServiceModel):
    ok: bool
    status_code: int | None = None
    detail: str
    latency_ms: float
    models: list[str] = Field(default_factory=list)
