"""Target adapters for FairLens v2.

``build_target`` accepts either ``sandbox:N`` (the validation adapters for the
seven synthetic models) or a repository-relative path to a YAML adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import httpx

from config_loader import REPO_ROOT

from targets.base import (
    ALL_PROBES,
    ProbeCapExceeded,
    TargetAdapter,
    TargetError,
    apply_probe_cap,
)
from targets.http import HTTPTargetAdapter
from targets.mapping import load_spec
from targets.sandbox import load_sandbox_target


def _adapter_class(spec: dict[str, Any]) -> type[HTTPTargetAdapter]:
    if spec.get("family") == "real":
        from targets.real.adapter import RealTargetAdapter

        return RealTargetAdapter
    return HTTPTargetAdapter


def build_target(
    reference: str,
    config: dict[str, Any],
    *,
    base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    env: Mapping[str, str] | None = None,
) -> HTTPTargetAdapter:
    """Resolve ``sandbox:N`` or a YAML path into an adapter."""

    cleaned = (reference or "").strip()
    if not cleaned:
        raise ValueError("target reference is empty")
    probe_cap = (config.get("targets") or {}).get("probe_cap")
    if cleaned.lower().startswith("sandbox:"):
        _, _, raw_model = cleaned.partition(":")
        try:
            model_id = int(raw_model)
        except ValueError as exc:
            raise ValueError(f"invalid sandbox target: {cleaned!r}") from exc
        return load_sandbox_target(
            model_id,
            base_url=base_url,
            probe_cap=probe_cap,
            transport=transport,
            env=env,
            sandbox_dir=(config.get("targets") or {}).get("sandbox_dir"),
        )
    path = Path(cleaned)
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("target adapter must live inside the repository") from exc
    spec = load_spec(resolved)
    adapter_class = _adapter_class(spec)
    adapter = adapter_class(spec, path=resolved, transport=transport, env=env)
    if base_url:
        adapter.base_url = base_url.rstrip("/")
    apply_probe_cap(adapter, probe_cap)
    return adapter

def sandbox_model_id(reference: str | None) -> int | None:
    """Return N for ``sandbox:N``, otherwise ``None``."""

    if not reference:
        return None
    cleaned = reference.strip()
    if not cleaned.lower().startswith("sandbox:"):
        return None
    _, _, raw_model = cleaned.partition(":")
    try:
        return int(raw_model)
    except ValueError:
        return None


__all__ = [
    "ALL_PROBES",
    "HTTPTargetAdapter",
    "ProbeCapExceeded",
    "TargetAdapter",
    "TargetError",
    "build_target",
    "load_sandbox_target",
    "sandbox_model_id",
]
