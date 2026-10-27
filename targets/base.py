"""Target adapter interface.

A target is any black-box decision service. The auditor only needs two
operations from it: a health check and a batch score that returns
``(approved, score)`` per applicant. Adapters own their transport concerns
(auth, rate limits, retries, timeouts) and enforce a hard per-audit probe cap.

Nothing in this package imports ``sandbox.models`` or ``sandbox.api``. Adapters
talk to targets over HTTP, exactly like the auditor does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from schemas import Applicant, ModelResponse


class TargetError(RuntimeError):
    """Raised for an unreachable or invalid target."""


class ProbeCapExceeded(TargetError):
    """Raised when an audit would exceed the hard probe cap."""


class TargetAdapter(ABC):
    """Minimal contract for a scored target."""

    name: str
    probe_cap: int

    @property
    @abstractmethod
    def probes_used(self) -> int:
        """Applicants sent to the target in this audit."""

    @abstractmethod
    def reset(self) -> None:
        """Start a new audit and reset the probe counter."""

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Return the target's health payload."""

    @abstractmethod
    async def score_batch(self, applicants: list[Applicant]) -> list[ModelResponse]:
        """Score a batch, returning one response per applicant in order."""

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "probe_cap": int(self.probe_cap),
            "probes_used": int(self.probes_used),
        }


def apply_probe_cap(adapter: TargetAdapter, cap: int | None) -> None:
    """Apply a global cap without weakening a stricter adapter-specific cap.

    ``None`` and non-positive values mean the global config does not constrain
    the adapter. A positive global cap is a ceiling, never a floor.
    """

    if cap is None:
        return
    value = int(cap)
    if value <= 0:
        return
    if adapter.probe_cap <= 0 or value < adapter.probe_cap:
        adapter.probe_cap = value
