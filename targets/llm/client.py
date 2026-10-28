"""Anthropic client wrapper for the R3c LLM screener.

The API key is read from the environment by the adapter and passed here; it is
never written to disk, a cache file, or a report. The product path has no mock
client. Tests inject a small fake that implements the same ``CompletionClient``
protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class CompletionClient(Protocol):
    model: str

    def complete(
        self, prompt: str, *, temperature: float, max_tokens: int
    ) -> Completion: ...


class AnthropicClient:
    """Thin wrapper around ``anthropic.Anthropic().messages.create``."""

    def __init__(self, *, api_key: str, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise ValueError("api_key is empty")
        if not model:
            raise ValueError("model is empty")
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "The anthropic package is required for the LLM target. "
                "Install it with: .venv\\Scripts\\python -m pip install anthropic"
            ) from exc
        self.model = model
        self._client = Anthropic(api_key=api_key, timeout=timeout)

    def complete(
        self, prompt: str, *, temperature: float, max_tokens: int
    ) -> Completion:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text
            for block in getattr(message, "content", [])
            if getattr(block, "type", "") == "text"
        )
        usage: Any = getattr(message, "usage", None)
        return Completion(
            text=text,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )
