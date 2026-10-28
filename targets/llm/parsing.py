"""Strict parsing of the LLM screener reply.

The contract is one JSON object with exactly two keys:

    {"approved": <boolean>, "score": <number from 0 to 1000>}

Anything else is a parse failure. Parse failures are returned with a reason and
counted by the adapter; they are never replaced with a default decision.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenDecision:
    approved: bool
    score: float


@dataclass(frozen=True)
class ParseFailure:
    reason: str


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite constant {value!r} is not valid JSON")


def parse_response(text: str) -> ScreenDecision | ParseFailure:
    stripped = text.strip()
    if not stripped:
        return ParseFailure("empty response")
    try:
        payload = json.loads(stripped, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        return ParseFailure(f"not valid JSON: {exc.msg}")
    except ValueError as exc:
        return ParseFailure(f"not valid JSON: {exc}")
    if not isinstance(payload, dict):
        return ParseFailure(f"expected a JSON object, got {type(payload).__name__}")
    keys = set(payload)
    if keys != {"approved", "score"}:
        return ParseFailure(
            "expected exactly the keys 'approved' and 'score'; "
            f"got {sorted(keys)}"
        )
    approved = payload["approved"]
    if not isinstance(approved, bool):
        return ParseFailure(
            f"'approved' must be a boolean, got {type(approved).__name__}"
        )
    score = payload["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return ParseFailure(
            f"'score' must be a number, got {type(score).__name__}"
        )
    if not math.isfinite(float(score)):
        return ParseFailure("'score' is not finite")
    if not 0.0 <= float(score) <= 1000.0:
        return ParseFailure(f"'score' {score} is outside 0..1000")
    return ScreenDecision(approved=approved, score=float(score))
