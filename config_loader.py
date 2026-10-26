"""Configuration loading for FairLens India.

All audit thresholds and planted effect sizes live in config.yaml. Code reads
them from here; nothing is tuned at runtime. An optional override path is
supported for the sensitivity analysis (materiality 1% / 3%), which writes a
temporary config copy rather than editing the pre-registered file.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    if not isinstance(config, dict):
        raise ValueError(f"Config at {config_path} must be a mapping")
    return config


def with_overrides(config: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy config and apply dotted-path overrides (e.g. audit.alpha)."""

    result = copy.deepcopy(config)
    for dotted, value in overrides.items():
        parts = dotted.split(".")
        cursor = result
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return result


def repo_path(relative: str | Path) -> Path:
    path = Path(relative)
    return path if path.is_absolute() else REPO_ROOT / path
