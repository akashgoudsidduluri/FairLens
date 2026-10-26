"""Number verification for LLM-written narratives.

Rule: every number in the narrative must already exist in the computed JSON.
We normalise formats (commas, percent signs, decimals, scientific notation,
rounding variants) before comparison. The LLM is never trusted to calculate.

This is deliberately conservative: if a number cannot be matched, the narrative
fails and the reporter regenerates once, then falls back to a deterministic
template that is checked by the same function.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

NUMBER_RE = re.compile(
    r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?"
)


def _iter_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            yield number
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_numbers(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_numbers(item)
        return
    # Strings are intentionally not parsed: hashes and IDs would poison the
    # allowed set with arbitrary digits.


def _norm(token: str) -> str:
    text = token.strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    text = text.lstrip("+")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text.lower()
    if number == 0:
        return "0"
    number = number.normalize()
    if abs(number) >= Decimal("0.0001"):
        return format(number, "f")
    return format(number, "e").lower()


def _formats(value: float) -> set[str]:
    out: set[str] = set()
    if not math.isfinite(value):
        return out
    out.add(str(value))
    out.add(format(value, "e").lower())
    for precision in range(0, 5):
        out.add(format(value, f".{precision}e").lower())
    if abs(value) >= 1e-4:
        for digits in range(0, 7):
            out.add(format(value, f".{digits}f"))
    return {_norm(item) for item in out}


def allowed_numbers(payload: Any) -> set[str]:
    """Build the set of normalised numeric strings permitted in a narrative."""

    allowed: set[str] = set()
    for value in _iter_numbers(payload):
        allowed |= _formats(value)
        if 0 <= value <= 1:
            allowed |= _formats(value * 100.0)
        allowed |= _formats(abs(value))
    return allowed


def extract_numbers(text: str) -> list[str]:
    return [match.group(0) for match in NUMBER_RE.finditer(text)]


def check_numbers(text: str, payload: Any) -> dict[str, Any]:
    """Return pass/fail plus the list of numbers not found in the JSON."""

    allowed = allowed_numbers(payload)
    tokens = extract_numbers(text)
    unknown: list[str] = []
    checked: list[str] = []
    for token in tokens:
        normalised = _norm(token)
        checked.append(token)
        if normalised not in allowed and normalised not in unknown:
            unknown.append(normalised)
    return {
        "passed": not unknown,
        "unknown": unknown,
        "checked": checked,
        "numeric_tokens": len(checked),
        "allowed_count": len(allowed),
    }
