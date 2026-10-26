"""Pydantic v2 data contracts shared by the sandbox, auditor, and UI.

This module is deliberately dependency-light: it may be imported by the
black-box auditor. It contains no scoring logic and no access to the sandbox
models.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Gender = Literal["female", "male"]
PincodeGroup = Literal["P1", "P2", "P3"]
NameGroup = Literal["N1", "N2", "N3"]
UrbanRural = Literal["urban", "rural"]
AgeBand = Literal["<35", "35-44", "45+"]
FindingStatus = Literal["candidate", "kept", "rejected", "immaterial"]
FindingKind = Literal["single_attribute", "intersectional"]


class Contract(BaseModel):
    """Base contract. Extra fields are rejected so typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


class Applicant(Contract):
    """One synthetic loan applicant.

    ``pincode_group``, ``name_group``, ``urban_rural`` and ``age_band`` are
    derived by ``sandbox.generator`` from lookup tables. They are repeated on
    the wire so the black-box API and the auditor share a stable contract.
    """

    id: str
    income: float = Field(gt=0, description="Annual income in synthetic INR")
    loan_amount: float = Field(gt=0, description="Requested loan in synthetic INR")
    credit_score: int = Field(ge=300, le=900)
    employment_years: float = Field(ge=0, le=60)
    age: int = Field(ge=21, le=65)
    gender: Gender
    pincode: str
    name: str
    pincode_group: PincodeGroup
    name_group: NameGroup
    urban_rural: UrbanRural
    age_band: AgeBand


class ModelResponse(Contract):
    approved: bool
    score: float


class TwinPair(Contract):
    """A counterfactual pair: identical except ``changed_attribute``."""

    pair_id: str
    original: Applicant
    twin: Applicant
    changed_attribute: str
    original_response: ModelResponse | None = None
    twin_response: ModelResponse | None = None


class Evidence(Contract):
    """Paired counterfactual evidence.

    b = original approved and twin rejected (harm direction)
    c = original rejected and twin approved (benefit direction)
    net_flip_rate = (b - c) / n
    p_raw = exact two-sided McNemar binomial test on b vs b+c at 0.5
    ci = seeded bootstrap percentile interval for (b - c) / n
    p_adjusted = Holm-adjusted p within the audit family
    """

    n: int = Field(ge=0)
    b: int = Field(ge=0)
    c: int = Field(ge=0)
    net_flip_rate: float = Field(ge=-1, le=1)
    ci_low: float = Field(ge=-1, le=1)
    ci_high: float = Field(ge=-1, le=1)
    p_raw: float = Field(ge=0, le=1)
    p_adjusted: float = Field(ge=0, le=1)


class Finding(Contract):
    id: str
    kind: FindingKind
    attribute_or_subgroup: str
    target_group: str
    comparison_group: str
    evidence: Evidence
    observational_gap: float
    observational_rates: dict[str, float] = Field(default_factory=dict)
    status: FindingStatus
    reason: str = ""
    matched_evidence: Evidence | None = None


class Check(Contract):
    name: str
    passed: bool
    detail: str


class SkepticVerdict(Contract):
    finding_id: str
    checks: list[Check]
    final_status: Literal["kept", "rejected", "immaterial"]
    reason: str


class AgentEvent(Contract):
    agent: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class ImpactEstimate(Contract):
    finding_id: str
    subgroup: str
    net_flip_rate: float
    per_10k: float
    ci_low_per_10k: float
    ci_high_per_10k: float
    explanation: str


class AuditReport(Contract):
    model_id: int
    config: dict[str, Any]
    findings: list[Finding]
    impact: list[ImpactEstimate] = Field(default_factory=list)
    mitigation_curve: list[dict[str, Any]] = Field(default_factory=list)
    narrative: str = ""
    number_check_result: dict[str, Any] = Field(default_factory=dict)
    observational: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CertificatePayload(Contract):
    version: int = 1
    model_id: int
    findings_hash: str
    report_hash: str
    config_hash: str
    approver: str
    decision: Literal["approve", "reject"]
    timestamp: str


class Certificate(Contract):
    index: int = Field(ge=0)
    prev_hash: str
    record_hash: str
    payload: dict[str, Any]
    created_at: datetime


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace, UTF-8 safe."""

    return json.dumps(
        to_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def to_jsonable(value: Any) -> Any:
    """Recursively convert numpy/pydantic/datetime values to JSON-safe types."""

    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    # numpy scalars expose .item(); avoid importing numpy in this contract module
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _SmokeModel(Contract):
    """Tiny model used by the phase-0 smoke test."""

    name: str
    count: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v
