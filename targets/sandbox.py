"""Validation adapters for the seven synthetic sandbox models.

Each ``targets/sandbox/model-N.yaml`` inherits from ``_sandbox.yaml`` and only
changes the ``model`` query parameter. The adapter does not import the sandbox
scoring code; it is an HTTP client like any other target.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import httpx

from config_loader import REPO_ROOT
from targets.base import apply_probe_cap
from targets.http import HTTPTargetAdapter

SANDBOX_DIR = Path(__file__).resolve().parent / "sandbox"
SANDBOX_MODELS = tuple(range(1, 8))


def load_sandbox_target(
    model_id: int,
    *,
    base_url: str | None = None,
    probe_cap: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    env: Mapping[str, str] | None = None,
    sandbox_dir: str | Path | None = None,
) -> HTTPTargetAdapter:
    if model_id not in SANDBOX_MODELS:
        raise ValueError(f"model_id must be one of {SANDBOX_MODELS}")
    directory = Path(sandbox_dir) if sandbox_dir else SANDBOX_DIR
    if not directory.is_absolute():
        directory = REPO_ROOT / directory
    path = directory / f"model-{model_id}.yaml"
    adapter = HTTPTargetAdapter.from_yaml(path, transport=transport, env=env)
    if base_url:
        adapter.base_url = base_url.rstrip("/")
    apply_probe_cap(adapter, probe_cap)
    return adapter
