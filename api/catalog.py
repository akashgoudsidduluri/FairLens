"""Model library catalog and connected-endpoint health checks.

The catalog is server-side so the browser cannot claim a target is available
when it is not. In particular the LLM screener reports its real availability
from ``ANTHROPIC_MODEL`` / ``ANTHROPIC_API_KEY``; if either is missing the card
says ``unavailable`` and Start Audit is disabled.

This module reads target YAML and metrics JSON directly. It never instantiates a
model, so loading the library is cheap and does not import numpy/joblib.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from config_loader import REPO_ROOT
from targets.llm.adapter import SUPPORTED_PROBES as LLM_SUPPORTED
from targets.llm.adapter import UNSUPPORTED_DETAILS as LLM_UNSUPPORTED
from targets.mapping import load_spec

from api.schemas import (
    EndpointCheckRequest,
    EndpointCheckResponse,
    TargetAvailability,
    TargetCard,
    TargetCatalog,
)

ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SANDBOX_TARGETS = [f"sandbox:{index}" for index in range(1, 8)]
REAL_TARGETS = (
    ("uci_credit_default", "targets/real/uci-credit-default.yaml"),
    ("adult_income", "targets/real/adult-income.yaml"),
)
ALL_PROBES = ["gender", "pincode_group", "name_group", "intersectional"]


def _artifact_available(model_name: str) -> bool:
    return (
        REPO_ROOT / "data" / "real" / "artifacts" / f"{model_name}.metrics.json"
    ).exists()


def _holdout_metric(model_name: str) -> str | None:
    path = REPO_ROOT / "data" / "real" / "artifacts" / f"{model_name}.metrics.json"
    if not path.exists():
        return None
    try:
        metrics = json.loads(path.read_text(encoding="utf-8"))
        accuracy = float(metrics["holdout"]["accuracy"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return f"holdout accuracy {accuracy:.4f}"


def _real_card(
    model_name: str,
    relative_path: str,
    first_model_id: int,
    planned_pairs: int,
) -> TargetCard:
    spec = load_spec(REPO_ROOT / relative_path)
    capabilities = spec.get("capabilities") or {}
    supported = [str(item) for item in capabilities.get("supported_probes") or []]
    unsupported = {
        str(key): str(value)
        for key, value in (capabilities.get("unsupported_probes") or {}).items()
    }
    available = _artifact_available(model_name)
    description = " ".join(str(spec.get("description") or "").split())
    return TargetCard(
        id=model_name,
        label=model_name.replace("_", " ").title(),
        kind="real",
        family="real",
        target=relative_path,
        model_id=first_model_id,
        description=description,
        supported_probes=supported,
        unsupported_probes=unsupported,
        availability=TargetAvailability(
            status="available" if available else "unavailable",
            reason="" if available else "trained artifacts are missing",
        ),
        planned_pairs=planned_pairs,
        probe_cap=int((spec.get("limits") or {}).get("probe_cap", 0)) or None,
        metric=_holdout_metric(model_name),
    )


def build_catalog(
    config: dict[str, Any], environ: Mapping[str, str] | None = None
) -> TargetCatalog:
    environment = os.environ if environ is None else environ
    planned_pairs = int((config.get("audit") or {}).get("n_pairs", 2000))
    probe_cap = int((config.get("targets") or {}).get("probe_cap", 100000))
    cards: list[TargetCard] = []

    for index, target in enumerate(SANDBOX_TARGETS, start=1):
        cards.append(
            TargetCard(
                id=f"sandbox-{index}",
                label=f"Validation model {index}",
                kind="validation",
                family="sandbox",
                target=target,
                model_id=index,
                description=(
                    "Synthetic black-box validation model. Its planted behaviour "
                    "is known to the frozen test suite, not to the auditor."
                ),
                supported_probes=list(ALL_PROBES),
                unsupported_probes={},
                availability=TargetAvailability(
                    status="configured",
                    reason="served by the sandbox validation service on port 8010",
                ),
                planned_pairs=planned_pairs,
                probe_cap=probe_cap,
                metric=f"validation suite {index}/7",
            )
        )

    for offset, (model_name, relative_path) in enumerate(REAL_TARGETS):
        cards.append(
            _real_card(
                model_name,
                relative_path,
                first_model_id=1 + offset,
                planned_pairs=planned_pairs,
            )
        )

    llm_config = config.get("llm") or {}
    model_env = str(llm_config.get("model_env", "ANTHROPIC_MODEL"))
    key_env = str(llm_config.get("api_key_env", "ANTHROPIC_API_KEY"))
    model = environment.get(model_env)
    key = environment.get(key_env)
    missing = [name for name, value in ((model_env, model), (key_env, key)) if not value]
    llm_available = not missing
    cards.append(
        TargetCard(
            id="llm-screener",
            label="LLM screener",
            kind="llm",
            family="llm",
            target="llm:screener",
            model_id=1,
            description=(
                "An Anthropic model asked to screen each applicant from a prompt. "
                "Its decision rules are not visible to us."
            ),
            supported_probes=sorted(LLM_SUPPORTED),
            unsupported_probes=dict(LLM_UNSUPPORTED),
            availability=TargetAvailability(
                status="available" if llm_available else "unavailable",
                reason=""
                if llm_available
                else f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set",
            ),
            planned_pairs=int(llm_config.get("pairs_per_probe", 24)),
            probe_cap=int(llm_config.get("max_calls_per_audit", 300)),
            metric=f"model {model}" if model else "model not configured",
        )
    )

    return TargetCatalog(targets=cards)


def check_endpoint(
    request: EndpointCheckRequest,
    *,
    environ: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> EndpointCheckResponse:
    """Health-check an endpoint from the server, never from the browser.

    Auth secrets stay in the server environment: the form only names the
    variable. A missing variable is a failed check with a clear reason.
    """

    environment = os.environ if environ is None else environ
    base_url = (request.base_url or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return EndpointCheckResponse(
            ok=False,
            detail="URL must start with http:// or https:// and include a host",
            latency_ms=0.0,
        )
    if parsed.username or parsed.password:
        return EndpointCheckResponse(
            ok=False,
            detail="Credentials must not be embedded in the URL; name an env var instead",
            latency_ms=0.0,
        )

    headers = {"Accept": "application/json"}
    if request.auth_env_var:
        name = request.auth_env_var.strip()
        if not ENV_NAME.fullmatch(name):
            return EndpointCheckResponse(
                ok=False,
                detail="Auth env var must be a valid environment variable name",
                latency_ms=0.0,
            )
        token = environment.get(name)
        if not token:
            return EndpointCheckResponse(
                ok=False,
                detail=f"environment variable {name} is not set on the API server",
                latency_ms=0.0,
            )
        headers[request.auth_header or "X-API-Key"] = token

    health_path = request.health_path or "/health"
    if not health_path.startswith("/"):
        health_path = "/" + health_path
    url = base_url + health_path
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=5.0, transport=transport) as client:
            response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return EndpointCheckResponse(
            ok=False,
            detail=f"could not reach {url}: {type(exc).__name__}: {exc}",
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    latency = round((time.perf_counter() - started) * 1000, 1)
    if response.status_code >= 400:
        return EndpointCheckResponse(
            ok=False,
            status_code=response.status_code,
            detail=f"health check returned HTTP {response.status_code}",
            latency_ms=latency,
        )
    models: list[str] = []
    try:
        payload = response.json()
        raw_models = payload.get("models") if isinstance(payload, dict) else None
        if isinstance(raw_models, list):
            models = [str(item) for item in raw_models]
    except ValueError:
        pass
    return EndpointCheckResponse(
        ok=True,
        status_code=response.status_code,
        detail="endpoint answered the health check",
        latency_ms=latency,
        models=models,
    )
