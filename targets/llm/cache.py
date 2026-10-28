"""Disk cache for LLM screener responses.

One file per prompt, named by a SHA-256 of the model, prompt, temperature, and
max tokens. The file holds a list of repeat samples, so a 3-repeat run keeps
three independent samples while a rerun reads the same three for free. The cache
is plain JSON and is safe to inspect or delete.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_VERSION = 1


class CacheCorrupt(RuntimeError):
    """Raised when a cache file exists but cannot be read."""


def prompt_key(
    *, model: str, prompt: str, temperature: float, max_tokens: int
) -> str:
    payload = json.dumps(
        {
            "version": CACHE_VERSION,
            "model": model,
            "prompt": prompt,
            "temperature": round(float(temperature), 6),
            "max_tokens": int(max_tokens),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def load(self, key: str) -> dict[str, Any] | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheCorrupt(
                f"Corrupt LLM cache file {path}. Delete it and rerun."
            ) from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("samples"), list
        ):
            raise CacheCorrupt(
                f"Invalid LLM cache file {path}. Delete it and rerun."
            )
        return payload

    def save(self, key: str, payload: dict[str, Any]) -> None:
        path = self.path_for(key)
        temporary = path.with_suffix(".json.part")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
