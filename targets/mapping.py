"""Template, environment, and YAML helpers for target adapters.

Adapters are declarative. A YAML file maps the canonical ``Applicant`` to a
request body and maps the target's response back to ``(approved, score)``.

Placeholders
------------
- ``${applicant.<field>}`` inside ``applicant_map`` pulls one field from an
  ``Applicant``.
- ``${applicants}`` expands to the mapped applicant list.
- ``${ENV_NAME}`` or ``${ENV_NAME:-default}`` reads the process environment.
  An unresolved variable without a default is an error, never an empty string.

Response paths
--------------
``$`` is the whole response body, ``$.results`` and ``results`` are equivalent
dotted paths, and numeric components index lists (``$.items.0``).
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
APPLICANT_FIELD = re.compile(r"^\$\{applicant\.([A-Za-z_][A-Za-z0-9_]*)\}$")


class MappingError(ValueError):
    """Raised when a template or response path cannot be resolved."""


class MissingEnvironmentVariable(MappingError):
    """Raised when a required environment variable is absent."""

    def __init__(self, name: str) -> None:
        super().__init__(f"environment variable {name!r} is not set")
        self.name = name


def expand_env(value: str, env: Mapping[str, str] | None = None) -> str:
    """Expand ``${VAR}`` and ``${VAR:-default}`` in a string."""

    source = os.environ if env is None else env

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in source:
            return str(source[name])
        if default is not None:
            return default
        raise MissingEnvironmentVariable(name)

    return ENV_PATTERN.sub(replace, value)


def resolve_template(
    value: Any,
    *,
    applicant: Any | None = None,
    applicants: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Recursively resolve placeholders in a YAML value."""

    if isinstance(value, str):
        if value == "${applicants}":
            if applicants is None:
                raise MappingError("${applicants} used outside an applicant batch")
            return applicants
        if value == "${applicant}":
            if applicant is None:
                raise MappingError("${applicant} used outside an applicant")
            return applicant
        field = APPLICANT_FIELD.match(value)
        if field:
            if applicant is None:
                raise MappingError("${applicant.*} used outside an applicant")
            try:
                return getattr(applicant, field.group(1))
            except AttributeError as exc:
                raise MappingError(
                    f"unknown applicant field {field.group(1)!r}"
                ) from exc
        if "${applicant." in value and applicant is None:
            raise MappingError("${applicant.*} used outside an applicant")
        expanded = expand_env(value, env)
        if applicant is None or "${applicant." not in value:
            return expanded

        def replace(match: re.Match[str]) -> str:
            try:
                return str(getattr(applicant, match.group(1)))
            except AttributeError as exc:
                raise MappingError(
                    f"unknown applicant field {match.group(1)!r}"
                ) from exc

        return re.sub(
            r"\$\{applicant\.([A-Za-z_][A-Za-z0-9_]*)\}",
            replace,
            expanded,
        )
    if isinstance(value, dict):
        return {
            key: resolve_template(
                item, applicant=applicant, applicants=applicants, env=env
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_template(
                item, applicant=applicant, applicants=applicants, env=env
            )
            for item in value
        ]
    return value


def get_path(data: Any, path: str | None) -> Any:
    """Read a dotted path from a JSON value."""

    if path in (None, "", "$"):
        return data
    cleaned = str(path)
    if cleaned.startswith("$."):
        cleaned = cleaned[2:]
    elif cleaned.startswith("$"):
        cleaned = cleaned[1:].lstrip(".")
    current = data
    for part in cleaned.split("."):
        if not part:
            continue
        if isinstance(current, dict):
            if part not in current:
                raise MappingError(f"response path {path!r} has no key {part!r}")
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise MappingError(
                    f"response path {path!r} has invalid list index {part!r}"
                ) from exc
        else:
            raise MappingError(
                f"response path {path!r} cannot descend into {type(current).__name__}"
            )
    return current


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""

    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_spec(path: str | Path, _seen: set[Path] | None = None) -> dict[str, Any]:
    """Load a YAML spec, following an optional ``base:`` file."""

    spec_path = Path(path).resolve()
    seen = set() if _seen is None else set(_seen)
    if spec_path in seen:
        raise MappingError(f"cyclic adapter base at {spec_path}")
    seen.add(spec_path)
    if not spec_path.exists():
        raise FileNotFoundError(f"target adapter not found: {spec_path}")
    with spec_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise MappingError(f"target adapter must be a mapping: {spec_path}")
    base_name = data.pop("base", None)
    if base_name:
        base_spec = load_spec(spec_path.parent / str(base_name), seen)
        data = deep_merge(base_spec, data)
    data["_path"] = str(spec_path)
    return data
