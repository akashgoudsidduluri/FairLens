"""R3c LLM screener target: names and regions only, strict JSON, cached.

Build it with ``build_target("llm:screener", config)``. With no
``ANTHROPIC_API_KEY`` the returned adapter reports ``unavailable``; it never
invents a decision. See ``targets/llm/README.md`` for the prompt, pools, caps,
and the caching and variance rules.
"""

from __future__ import annotations

from targets.llm.adapter import (
    LLMCapExceeded,
    LLMTargetAdapter,
    LLMUnavailable,
    LLMUnparseable,
    ScreenResult,
    build_llm_target,
)
from targets.llm.cache import ResponseCache, prompt_key
from targets.llm.parsing import ParseFailure, ScreenDecision, parse_response
from targets.llm.prompt import build_prompt, prompt_fields
from targets.llm.variance import (
    applicant_disagreement,
    pair_flip_series,
    pair_variance,
    summarize_variance,
)

__all__ = [
    "LLMCapExceeded",
    "LLMTargetAdapter",
    "LLMUnavailable",
    "LLMUnparseable",
    "ParseFailure",
    "ResponseCache",
    "ScreenDecision",
    "ScreenResult",
    "applicant_disagreement",
    "build_llm_target",
    "build_prompt",
    "pair_flip_series",
    "pair_variance",
    "parse_response",
    "prompt_fields",
    "prompt_key",
    "summarize_variance",
]
