"""R3c LLM screener target.

The target sends one loan-screening prompt per applicant to an Anthropic model.
It is an in-process ``TargetAdapter`` (no HTTP hop), because each prompt is an
external API call and a local HTTP service would only add a layer.

Design rules, fixed before the audit (see ``expected_findings.md``):

- Temperature 0. Each applicant is screened ``repeats`` times (default 3).
- A pair's outcome is the majority of its parseable repeats. Fewer than a
  quorum of parseable repeats, or a tie, is unresolved: counted and reported,
  never turned into a silent decision.
- Only ``name_group`` and ``pincode_group`` probes are defined. A name twin
  changes the ``Name:`` line only; a region twin changes the ``Region:`` line
  only. Everything else is byte-identical.
- Responses are cached by prompt hash with one slot per repeat, so reruns are
  free and reproduce the same samples.
- Hard API-call and cost caps are enforced before each call. Unparseable
  outputs are counted. No API key means "unavailable", not a fake answer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from config_loader import REPO_ROOT
from schemas import Applicant, ModelResponse
from targets.base import ProbeCapExceeded, TargetAdapter, TargetError
from targets.llm.cache import ResponseCache, prompt_key
from targets.llm.client import AnthropicClient, CompletionClient
from targets.llm.parsing import ParseFailure, ScreenDecision, parse_response
from targets.llm.prompt import build_prompt, diff_fields

SUPPORTED_PROBES = frozenset({"name_group", "pincode_group"})

UNSUPPORTED_DETAILS = {
    "gender": (
        "The R3c screener varies names and regions only. Gender is held fixed "
        "in every prompt, so a gender twin is not defined for this target."
    ),
    "intersectional": (
        "The screener has no urban/rural input, and the cost cap cannot cover "
        "the 12-cell scan. Intersectional probes are not defined."
    ),
}


class LLMUnavailable(TargetError):
    """Raised when the model or API key is missing."""


class LLMUnparseable(TargetError):
    """Raised when a screener reply cannot be parsed to a decision."""


class LLMCapExceeded(ProbeCapExceeded):
    """Raised before a call that would exceed the probe or cost cap."""


@dataclass(frozen=True)
class ScreenResult:
    prompt: str
    approvals: tuple[bool | None, ...]
    scores: tuple[float | None, ...]
    errors: tuple[str, ...]
    majority: bool | None
    score: float | None
    valid_n: int
    unresolved_reason: str = ""


def _settings(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repeats": max(1, int(spec.get("repeats", 3))),
        "temperature": float(spec.get("temperature", 0.0)),
        "max_tokens": int(spec.get("max_tokens", 64)),
        "max_calls": int(spec.get("max_calls_per_audit", 300)),
        "max_cost_usd": float(spec.get("max_cost_usd", 1.00)),
        "input_price": float(spec.get("input_cost_per_mtok_usd", 3.00)),
        "output_price": float(spec.get("output_cost_per_mtok_usd", 15.00)),
        "cache_dir": str(spec.get("cache_dir", "data/llm_cache")),
        "pairs_per_probe": int(spec.get("pairs_per_probe", 24)),
    }


class LLMTargetAdapter(TargetAdapter):
    def __init__(
        self,
        spec: Mapping[str, Any],
        *,
        client: CompletionClient | None = None,
        model: str | None = None,
        cache: ResponseCache | None = None,
        unavailable_reason: str = "",
    ) -> None:
        self._spec = _settings(spec)
        self.name = "llm-screener"
        self.model = model
        self._client = client
        self._cache = cache or ResponseCache(self._cache_path(self._spec["cache_dir"]))
        self.supported_probes = SUPPORTED_PROBES
        self.unsupported_details = dict(UNSUPPORTED_DETAILS)
        self.supports_mitigation = False
        self.probe_cap = int(self._spec["max_calls"])
        self._unavailable_reason = unavailable_reason
        if self._client is None and not self._unavailable_reason:
            self._unavailable_reason = "no LLM client is configured"
        self._calls = 0
        self._cost = 0.0
        self._cache_hits = 0
        self._parse_failures = 0
        self._unresolved = 0

    @staticmethod
    def _cache_path(raw: str) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else REPO_ROOT / path

    # ------------------------------------------------------------------ stats
    @property
    def probes_used(self) -> int:
        """API calls made in this audit. Cache hits are free and not counted."""

        return self._calls

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    @property
    def parse_failures(self) -> int:
        return self._parse_failures

    @property
    def unresolved(self) -> int:
        return self._unresolved

    @property
    def cost_usd(self) -> float:
        return round(self._cost, 6)

    @property
    def repeats(self) -> int:
        return int(self._spec["repeats"])

    @property
    def pairs_per_probe(self) -> int:
        return int(self._spec["pairs_per_probe"])

    def available(self) -> bool:
        return self._client is not None

    def reset(self) -> None:
        self._calls = 0
        self._cost = 0.0
        self._cache_hits = 0
        self._parse_failures = 0
        self._unresolved = 0

    async def health(self) -> dict[str, Any]:
        base = {
            "models": ["llm-screener"],
            "provider": "anthropic",
            "model": self.model,
            "repeats": self.repeats,
            "temperature": self._spec["temperature"],
            "max_calls_per_audit": self._spec["max_calls"],
            "max_cost_usd": self._spec["max_cost_usd"],
            "cache_dir": self._cache.directory.relative_to(REPO_ROOT).as_posix()
            if self._cache.directory.is_relative_to(REPO_ROOT)
            else str(self._cache.directory),
        }
        if not self.available():
            return {
                "status": "unavailable",
                "reason": self._unavailable_reason,
                **base,
            }
        return {"status": "ok", **base}

    # ------------------------------------------------------------------- cost
    def _estimate_cost(self, prompt: str) -> float:
        input_tokens = max(1.0, len(prompt) / 4.0)
        output_tokens = float(self._spec["max_tokens"])
        return (
            input_tokens * self._spec["input_price"]
            + output_tokens * self._spec["output_price"]
        ) / 1_000_000.0

    def _actual_cost(self, input_tokens: int, output_tokens: int, text: str) -> float:
        if input_tokens or output_tokens:
            return (
                input_tokens * self._spec["input_price"]
                + output_tokens * self._spec["output_price"]
            ) / 1_000_000.0
        # Conservative fallback if a provider omits usage: prompt chars/4 in,
        # reply chars/4 out.
        return (
            max(1, len(text) // 4) * self._spec["output_price"]
        ) / 1_000_000.0

    # ------------------------------------------------------------------ cache
    def _sample(self, prompt: str, index: int) -> dict[str, Any]:
        if not self.available():
            raise LLMUnavailable(self._unavailable_reason)
        assert self._client is not None
        model = self.model or getattr(self._client, "model", "") or "unknown"
        key = prompt_key(
            model=model,
            prompt=prompt,
            temperature=self._spec["temperature"],
            max_tokens=self._spec["max_tokens"],
        )
        payload = self._cache.load(key)
        if payload is None:
            payload = {
                "version": 1,
                "key": key,
                "model": model,
                "temperature": self._spec["temperature"],
                "max_tokens": self._spec["max_tokens"],
                "prompt": prompt,
                "samples": [],
            }
        samples: list[dict[str, Any]] = payload["samples"]
        if len(samples) > index:
            self._cache_hits += 1
            return samples[index]

        while len(samples) <= index:
            if self._calls >= self._spec["max_calls"]:
                raise LLMCapExceeded(
                    "LLM probe cap reached: "
                    f"{self._calls} calls >= {self._spec['max_calls']} per audit"
                )
            estimate = self._estimate_cost(prompt)
            if self._cost + estimate > self._spec["max_cost_usd"]:
                raise LLMCapExceeded(
                    "LLM cost cap reached: spent "
                    f"${self._cost:.4f}, next call up to ${estimate:.4f}, "
                    f"cap ${self._spec['max_cost_usd']:.2f}"
                )
            completion = self._client.complete(
                prompt,
                temperature=self._spec["temperature"],
                max_tokens=self._spec["max_tokens"],
            )
            cost = self._actual_cost(
                completion.input_tokens, completion.output_tokens, completion.text
            )
            self._calls += 1
            self._cost += cost
            samples.append(
                {
                    "text": completion.text,
                    "input_tokens": int(completion.input_tokens),
                    "output_tokens": int(completion.output_tokens),
                    "cost_usd": round(cost, 8),
                }
            )
            self._cache.save(key, payload)
        return samples[index]

    # ----------------------------------------------------------------- screen
    def screen(self, applicant: Applicant) -> ScreenResult:
        prompt = build_prompt(applicant)
        approvals: list[bool | None] = []
        scores: list[float | None] = []
        errors: list[str] = []
        for index in range(self.repeats):
            sample = self._sample(prompt, index)
            parsed = parse_response(str(sample.get("text", "")))
            if isinstance(parsed, ParseFailure):
                approvals.append(None)
                scores.append(None)
                errors.append(parsed.reason)
                self._parse_failures += 1
            else:
                assert isinstance(parsed, ScreenDecision)
                approvals.append(parsed.approved)
                scores.append(parsed.score)

        valid = [value for value in approvals if value is not None]
        quorum = (self.repeats // 2) + 1
        if len(valid) < quorum:
            self._unresolved += 1
            return ScreenResult(
                prompt=prompt,
                approvals=tuple(approvals),
                scores=tuple(scores),
                errors=tuple(errors),
                majority=None,
                score=None,
                valid_n=len(valid),
                unresolved_reason=(
                    f"only {len(valid)} of {self.repeats} repeats parsed; "
                    f"quorum is {quorum}"
                ),
            )
        approve = sum(1 for value in valid if value)
        reject = len(valid) - approve
        if approve == reject:
            self._unresolved += 1
            return ScreenResult(
                prompt=prompt,
                approvals=tuple(approvals),
                scores=tuple(scores),
                errors=tuple(errors),
                majority=None,
                score=None,
                valid_n=len(valid),
                unresolved_reason=f"tie: {approve} approve, {reject} reject",
            )
        majority = approve > reject
        valid_scores = [value for value in scores if value is not None]
        return ScreenResult(
            prompt=prompt,
            approvals=tuple(approvals),
            scores=tuple(scores),
            errors=tuple(errors),
            majority=majority,
            score=float(median(valid_scores)) if valid_scores else None,
            valid_n=len(valid),
        )

    async def score_batch(self, applicants: list[Applicant]) -> list[ModelResponse]:
        if not self.available():
            raise LLMUnavailable(self._unavailable_reason)
        responses: list[ModelResponse] = []
        for applicant in applicants:
            result = self.screen(applicant)
            if result.majority is None or result.score is None:
                raise LLMUnparseable(
                    f"applicant {applicant.id}: {result.unresolved_reason}; "
                    f"errors={list(result.errors)}"
                )
            responses.append(
                ModelResponse(approved=bool(result.majority), score=result.score)
            )
        return responses

    # ----------------------------------------------------------- feasibility
    def validate_pair(
        self, original: Applicant, twin: Applicant, attribute: str
    ) -> tuple[bool, str]:
        expected = {
            "name_group": ["name"],
            "pincode_group": ["region"],
        }
        if attribute not in expected:
            return False, (
                f"probe {attribute!r} is not defined for the LLM screener; "
                "only names and regions are varied"
            )
        changed = diff_fields(original, twin)
        if changed != expected[attribute]:
            return False, (
                f"{attribute} twin changed prompt fields {changed or 'none'}; "
                f"expected exactly {expected[attribute]}"
            )
        if build_prompt(original) == build_prompt(twin):
            return False, f"{attribute} twin produced an identical prompt"
        return True, ""

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "provider": "anthropic",
            "model": self.model,
            "available": self.available(),
            "repeats": self.repeats,
            "cache_hits": self.cache_hits,
            "parse_failures": self.parse_failures,
            "unresolved": self.unresolved,
            "cost_usd": self.cost_usd,
            "supported_probes": sorted(self.supported_probes),
        }


def build_llm_target(
    reference: str,
    config: dict[str, Any],
    *,
    client: CompletionClient | None = None,
    env: Mapping[str, str] | None = None,
) -> LLMTargetAdapter:
    """Resolve ``llm:screener`` into an adapter, available or unavailable."""

    cleaned = (reference or "").strip().lower()
    if cleaned not in {"llm", "llm:screener", "screener"}:
        raise ValueError(
            f"unknown LLM target reference {reference!r}; use 'llm:screener'"
        )
    spec = _settings(config.get("llm") or {})
    environment = os.environ if env is None else env
    model = environment.get(str((config.get("llm") or {}).get("model_env", "ANTHROPIC_MODEL")))
    key = environment.get(
        str((config.get("llm") or {}).get("api_key_env", "ANTHROPIC_API_KEY"))
    )
    cache_dir = environment.get("FAIRLENS_LLM_CACHE", spec["cache_dir"])
    cache = ResponseCache(LLMTargetAdapter._cache_path(cache_dir))

    reason = ""
    if client is None:
        missing: list[str] = []
        if not model:
            missing.append("ANTHROPIC_MODEL")
        if not key:
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            verb = "is" if len(missing) == 1 else "are"
            reason = f"{' and '.join(missing)} {verb} not set"
        else:
            client = AnthropicClient(api_key=key, model=model)

    return LLMTargetAdapter(
        config.get("llm") or {},
        client=client,
        model=model,
        cache=cache,
        unavailable_reason=reason,
    )
