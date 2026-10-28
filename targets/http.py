"""Declarative HTTP target adapter.

Example YAML::

    name: my-lender
    base_url: "${LENDER_URL:-https://example.test}"
    auth:
      type: header            # none | header | bearer | query
      header_name: X-API-Key
      token_env: LENDER_API_KEY
    request:
      method: POST
      path: /v1/decisions
      query: {product: personal_loan}
      headers: {Accept: application/json}
      applicant_map:
        annual_income: "${applicant.income}"
        credit: "${applicant.credit_score}"
        applicant_ref: "${applicant.id}"
      body:
        applicants: "${applicants}"
    response:
      items: "$.decisions"
      approved: "result"
      approved_true: ["APPROVE", true]
      score: "score"
    limits:
      probe_cap: 100000
      rate_limit_per_second: 20
      max_retries: 3
      backoff_seconds: 0.25
      timeout_seconds: 20

The adapter never retries a 4xx, always retries 5xx and transport errors, and
counts applicants toward the probe cap only after a successful mapped response.
Each audit gets its own adapter instance, so the cap and rate limiter reset.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Mapping

import httpx

from schemas import Applicant, ModelResponse

from targets.base import ALL_PROBES, ProbeCapExceeded, TargetAdapter, TargetError
from targets.mapping import MappingError, get_path, load_spec, resolve_template


class _Retryable(TargetError):
    """Internal marker for errors worth retrying."""


def _as_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TargetError("request.headers must be a mapping")
    return {str(key): str(item) for key, item in value.items()}


def _as_params(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargetError("request.query must be a mapping")
    return dict(value)


def _coerce_bool(value: Any, true_values: list[Any]) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower()
        allowed = {str(item).strip().lower() for item in true_values}
        allowed.update({"true", "approved", "approve", "yes", "1", "y"})
        return cleaned in allowed
    return value in true_values


class HTTPTargetAdapter(TargetAdapter):
    def __init__(
        self,
        spec: dict[str, Any],
        *,
        path: str | Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(spec, dict):
            raise TargetError("target spec must be a mapping")
        self.spec = spec
        self.path = str(path) if path else None
        self.name = str(spec.get("name") or "http-target")
        self._env = env
        limits = spec.get("limits") or {}
        self.probe_cap = int(limits.get("probe_cap", 100_000))
        self.rate_limit_per_second = float(limits.get("rate_limit_per_second", 0))
        self.max_retries = max(0, int(limits.get("max_retries", 0)))
        self.backoff_seconds = max(0.0, float(limits.get("backoff_seconds", 0.25)))
        self.timeout_seconds = float(limits.get("timeout_seconds", 20))
        self.base_url = resolve_template(
            str(spec.get("base_url") or ""), env=self._env
        ).rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise TargetError(
                f"target {self.name!r} has an invalid base_url: {self.base_url!r}"
            )
        self._transport = transport
        self._probes_used = 0
        self._last_request = 0.0
        capabilities = spec.get("capabilities") or {}
        declared = capabilities.get("supported_probes")
        self.supported_probes = (
            ALL_PROBES if declared is None else frozenset(str(p) for p in declared)
        )
        self.unsupported_details = {
            str(key): str(value)
            for key, value in (capabilities.get("unsupported_probes") or {}).items()
        }
        self.supports_mitigation = bool(capabilities.get("supports_mitigation", True))

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        env: Mapping[str, str] | None = None,
    ) -> "HTTPTargetAdapter":
        spec = load_spec(path)
        return cls(spec, path=path, transport=transport, env=env)

    @property
    def probes_used(self) -> int:
        return self._probes_used

    def reset(self) -> None:
        self._probes_used = 0
        self._last_request = 0.0

    # ------------------------------------------------------------------ request
    def _auth(self, headers: dict[str, str], params: dict[str, Any]) -> None:
        auth = self.spec.get("auth") or {}
        kind = str(auth.get("type", "none")).lower()
        if kind == "none":
            return
        token_env = auth.get("token_env")
        if not token_env:
            raise TargetError("auth.token_env is required when auth.type is not none")
        source = os.environ if self._env is None else self._env
        token = source.get(str(token_env))
        if token is None:
            raise TargetError(
                f"target {self.name!r} needs environment variable {token_env!r}"
            )
        if kind == "header":
            header_name = str(auth.get("header_name", "X-API-Key"))
            headers[header_name] = f"{auth.get('prefix', '')}{token}"
        elif kind == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif kind == "query":
            params[str(auth.get("param", "api_key"))] = token
        else:
            raise TargetError(f"unsupported auth.type: {kind!r}")

    def _mapped_applicants(self, applicants: list[Applicant]) -> list[dict[str, Any]]:
        request = self.spec.get("request") or {}
        applicant_map = request.get("applicant_map")
        if not applicant_map:
            return [a.model_dump(mode="json") for a in applicants]
        if not isinstance(applicant_map, dict):
            raise TargetError("request.applicant_map must be a mapping")
        mapped: list[dict[str, Any]] = []
        for applicant in applicants:
            mapped.append(
                {
                    str(key): resolve_template(
                        template, applicant=applicant, env=self._env
                    )
                    for key, template in applicant_map.items()
                }
            )
        return mapped

    def _build_request(
        self, applicants: list[Applicant]
    ) -> tuple[str, str, dict[str, str], dict[str, Any], Any]:
        request = self.spec.get("request") or {}
        method = str(request.get("method", "POST")).upper()
        path = str(request.get("path", "/score"))
        url = f"{self.base_url}{path}"
        headers = _as_headers(
            resolve_template(request.get("headers", {}), env=self._env)
        )
        params = _as_params(
            resolve_template(request.get("query", {}), env=self._env)
        )
        self._auth(headers, params)
        mapped = self._mapped_applicants(applicants)
        body = resolve_template(
            request.get("body", "${applicants}"),
            applicants=mapped,
            env=self._env,
        )
        return method, url, headers, params, body

    # ----------------------------------------------------------------- response
    def _map_item(self, item: Any, response: dict[str, Any]) -> ModelResponse:
        score_path = response.get("score", "score")
        threshold = response.get("approval_threshold")
        approved_path = response.get("approved", "approved")
        true_values = list(
            response.get(
                "approved_true",
                [True, 1, "true", "approved", "approve", "yes", "1"],
            )
        )
        if isinstance(item, dict):
            score = float(get_path(item, score_path))
            approved_raw = (
                get_path(item, approved_path) if approved_path is not None else None
            )
        else:
            score = float(item)
            approved_raw = None
        if threshold is not None:
            approved = score >= float(threshold)
        else:
            if approved_raw is None:
                raise TargetError(
                    "response has no approved field and no approval_threshold"
                )
            approved = _coerce_bool(approved_raw, true_values)
        return ModelResponse(approved=approved, score=score)

    # ------------------------------------------------------------------ network
    async def _throttle(self) -> None:
        if self.rate_limit_per_second <= 0:
            return
        interval = 1.0 / self.rate_limit_per_second
        now = time.monotonic()
        wait = self._last_request + interval - now
        if wait > 0:
            await asyncio.sleep(wait)
            now = time.monotonic()
        self._last_request = now

    async def health(self) -> dict[str, Any]:
        health = self.spec.get("health") or {}
        path = str(health.get("path", "/health"))
        headers = _as_headers(
            resolve_template(health.get("headers", {}), env=self._env)
        )
        params = _as_params(
            resolve_template(health.get("query", {}), env=self._env)
        )
        self._auth(headers, params)
        last_error: Exception | None = None
        async with httpx.AsyncClient(
            timeout=min(self.timeout_seconds, 5.0),
            transport=self._transport,
        ) as client:
            for attempt in range(self.max_retries + 1):
                await self._throttle()
                try:
                    response = await client.get(
                        f"{self.base_url}{path}", headers=headers, params=params
                    )
                    if response.status_code >= 500:
                        raise _Retryable(
                            f"target {self.name!r} health returned HTTP "
                            f"{response.status_code}"
                        )
                    if response.status_code >= 400:
                        raise TargetError(
                            f"target {self.name!r} health rejected with HTTP "
                            f"{response.status_code}"
                        )
                    data = response.json()
                    if not isinstance(data, dict):
                        raise TargetError(
                            f"target {self.name!r} health payload is not an object"
                        )
                    return data
                except _Retryable as exc:
                    last_error = exc
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(self.backoff_seconds * (2**attempt))
        raise TargetError(
            f"target {self.name!r} health check failed after "
            f"{self.max_retries + 1} attempt(s): {last_error}"
        ) from last_error

    async def score_batch(self, applicants: list[Applicant]) -> list[ModelResponse]:
        if not applicants:
            return []
        if self.probe_cap > 0 and self._probes_used + len(applicants) > self.probe_cap:
            raise ProbeCapExceeded(
                f"target {self.name!r} probe cap {self.probe_cap} exceeded: "
                f"{self._probes_used} used, {len(applicants)} requested"
            )
        try:
            method, url, headers, params, body = self._build_request(applicants)
        except MappingError as exc:
            raise TargetError(f"target {self.name!r} request mapping failed: {exc}") from exc
        response_spec = self.spec.get("response") or {}
        last_error: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, transport=self._transport
        ) as client:
            for attempt in range(self.max_retries + 1):
                await self._throttle()
                try:
                    response = await client.request(
                        method, url, headers=headers, params=params, json=body
                    )
                    if response.status_code >= 500:
                        raise _Retryable(
                            f"target {self.name!r} returned HTTP "
                            f"{response.status_code}: {response.text[:200]}"
                        )
                    if response.status_code >= 400:
                        raise TargetError(
                            f"target {self.name!r} rejected the request "
                            f"(HTTP {response.status_code}): {response.text[:200]}"
                        )
                    payload = response.json()
                    items = get_path(payload, response_spec.get("items", "$"))
                    if not isinstance(items, list):
                        raise _Retryable(
                            f"target {self.name!r} response is not a list at "
                            f"{response_spec.get('items', '$')!r}"
                        )
                    if len(items) != len(applicants):
                        raise _Retryable(
                            f"target {self.name!r} returned {len(items)} decisions "
                            f"for {len(applicants)} applicants"
                        )
                    mapped = [self._map_item(item, response_spec) for item in items]
                    self._probes_used += len(applicants)
                    return mapped
                except _Retryable as exc:
                    last_error = exc
                except (httpx.HTTPError, ValueError, MappingError) as exc:
                    last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(self.backoff_seconds * (2**attempt))
        raise TargetError(
            f"target {self.name!r} failed after {self.max_retries + 1} "
            f"attempt(s): {last_error}"
        ) from last_error
