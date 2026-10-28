"""HTTP adapter for a model trained on real public data.

The adapter is a thin HTTP client, exactly like the sandbox adapters. The only
extra responsibility is twin feasibility: both applicants are mapped through
the same feature function the serving process uses, checked against the
training ranges, and a gender twin must change exactly the ``sex`` feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import httpx

from schemas import Applicant
from targets.http import HTTPTargetAdapter
from targets.real.features import probe_capabilities, validate_pair
from targets.real.models import load_real_model


class RealTargetAdapter(HTTPTargetAdapter):
    """Adapter with dataset-aware twin validation and no offset mitigation."""

    def __init__(
        self,
        spec: dict[str, Any],
        *,
        path: str | Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(spec, path=path, transport=transport, env=env)
        self.real_model = str(spec.get("real_model") or "")
        if not self.real_model:
            raise ValueError("real target spec must set real_model")
        capabilities = spec.get("capabilities") or {}
        self.supported_probes = frozenset(capabilities.get("supported_probes", ["gender"]))
        self.unsupported_details = dict(capabilities.get("unsupported_probes") or {})
        self.supports_mitigation = False
        # Fail fast if the artifact is missing, rather than mid-audit.
        self._profile = load_real_model(self.real_model).profile

    def validate_pair(
        self,
        original: Applicant,
        twin: Applicant,
        attribute: str,
    ) -> tuple[bool, str]:
        return validate_pair(
            self.real_model, original, twin, attribute, self._profile
        )

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "real_model": self.real_model,
            "supported_probes": sorted(self.supported_probes),
        }


def capabilities_for(model_name: str) -> dict[str, Any]:
    return probe_capabilities(model_name)
