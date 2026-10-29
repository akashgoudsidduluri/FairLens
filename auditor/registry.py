"""Attribute registry for the generalized search (R5).

The registry is loaded from ``config.yaml`` and is the single place that says
what an attribute is allowed to do:

- **treatment**: the attribute can be the signal flipped between twins.
- **context**: the attribute can describe the subgroup where an effect appears.

Legitimate attributes (income, credit score, loan amount, employment years) are
context-only. They are used for conditioning and for the income-matched check,
and are never reported as bias on their own. This module contains no scoring
logic and never imports the sandbox models.

Binning rule for ``bands`` attributes: ``edges`` are the exclusive upper bounds
of every bin except the last one. With labels ``[low, mid, high]`` and edges
``[400000, 900000]`` the bins are ``value < 400000``, ``400000 <= value <
900000`` and ``value >= 900000``. ``numpy.searchsorted(edges, value, "right")``
therefore returns the label index directly. Edges must be strictly increasing
and there must be exactly ``len(labels) - 1`` of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from scipy.stats import norm

from schemas import Applicant

ROLES = frozenset({"protected", "proxy", "legitimate"})
KINDS = frozenset({"categorical", "bands"})
APPLICANT_SOURCES = frozenset(
    {
        "gender",
        "age",
        "pincode_group",
        "name_group",
        "urban_rural",
        "income",
        "credit_score",
        "loan_amount",
        "employment_years",
    }
)


class RegistryError(ValueError):
    """Raised when the attribute registry is incomplete or inconsistent."""


@dataclass(frozen=True)
class AttributeSpec:
    name: str
    type: str
    role: str
    source: str
    treatment: bool
    context: bool
    labels: tuple[str, ...] = ()
    edges: tuple[float, ...] = ()
    values: tuple[str, ...] = ()
    treatment_levels: tuple[str, ...] = ()
    comparison_level: str | None = None
    feasibility: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @property
    def is_legitimate(self) -> bool:
        return self.role == "legitimate"

    @property
    def choices(self) -> tuple[str, ...]:
        return self.values if self.type == "categorical" else self.labels

    def bin_value(self, value: Any) -> str:
        """Return the fixed bin label for a raw numeric or categorical value."""

        if self.type == "categorical":
            text = str(value)
            if text not in self.values:
                raise RegistryError(
                    f"{self.name}: {text!r} is not one of {list(self.values)}"
                )
            return text
        number = float(value)
        index = int(np.searchsorted(np.asarray(self.edges), number, side="right"))
        index = min(max(index, 0), len(self.labels) - 1)
        return self.labels[index]


@dataclass(frozen=True)
class AttributeRegistry:
    specs: dict[str, AttributeSpec]

    def get(self, name: str) -> AttributeSpec:
        try:
            return self.specs[name]
        except KeyError as exc:
            raise RegistryError(f"unknown attribute: {name!r}") from exc

    def bin_value(self, name: str, applicant: Applicant) -> str:
        spec = self.get(name)
        return spec.bin_value(getattr(applicant, spec.source))

    def cell_key(self, applicant: Applicant, context: Iterable[str]) -> tuple[str, ...]:
        return tuple(self.bin_value(name, applicant) for name in context)

    def treatment_attributes(self) -> list[str]:
        return [name for name, spec in self.specs.items() if spec.treatment]

    def context_attributes(self, treatment: str | None = None) -> list[str]:
        return [
            name
            for name, spec in self.specs.items()
            if spec.context and name != treatment
        ]

    def legitimate_attributes(self) -> list[str]:
        return [name for name, spec in self.specs.items() if spec.is_legitimate]

    def label(self, name: str, value: str) -> str:
        return f"{name}={value}"


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise RegistryError(f"{where}: missing required key {key!r}")
    return mapping[key]


def _spec(name: str, raw: dict[str, Any]) -> AttributeSpec:
    if not isinstance(raw, dict):
        raise RegistryError(f"attributes.{name}: must be a mapping")
    where = f"attributes.{name}"
    kind = str(_require(raw, "type", where))
    role = str(_require(raw, "role", where))
    source = str(_require(raw, "source", where))
    if kind not in KINDS:
        raise RegistryError(f"{where}: type must be one of {sorted(KINDS)}")
    if role not in ROLES:
        raise RegistryError(f"{where}: role must be one of {sorted(ROLES)}")
    if source not in APPLICANT_SOURCES:
        raise RegistryError(f"{where}: source {source!r} is not an Applicant field")

    treatment = bool(raw.get("treatment", False))
    context = bool(raw.get("context", True))
    if treatment and role == "legitimate":
        raise RegistryError(
            f"{where}: legitimate attributes are context-only and cannot be a treatment"
        )

    labels: tuple[str, ...] = ()
    edges: tuple[float, ...] = ()
    values: tuple[str, ...] = ()
    if kind == "categorical":
        values = tuple(str(item) for item in _require(raw, "values", where))
        if not values:
            raise RegistryError(f"{where}: values cannot be empty")
        if len(set(values)) != len(values):
            raise RegistryError(f"{where}: values must be unique")
    else:
        labels = tuple(str(item) for item in _require(raw, "labels", where))
        edges = tuple(float(item) for item in _require(raw, "edges", where))
        if len(labels) != len(edges) + 1:
            raise RegistryError(
                f"{where}: need len(labels) == len(edges) + 1 "
                f"(got {len(labels)} labels and {len(edges)} edges)"
            )
        if any(b <= a for a, b in zip(edges, edges[1:])):
            raise RegistryError(f"{where}: edges must be strictly increasing")
        if len(set(labels)) != len(labels) or any(not label for label in labels):
            raise RegistryError(f"{where}: labels must be non-empty and unique")

    levels = tuple(str(item) for item in raw.get("treatment_levels") or ())
    comparison = raw.get("comparison_level")
    comparison = str(comparison) if comparison is not None else None
    choices = values if kind == "categorical" else labels
    if treatment:
        if not levels:
            raise RegistryError(f"{where}: a treatment needs treatment_levels")
        unknown = [level for level in levels if level not in choices]
        if unknown:
            raise RegistryError(f"{where}: unknown treatment_levels {unknown}")
        if comparison is None:
            raise RegistryError(f"{where}: a treatment needs comparison_level")
        if comparison not in choices:
            raise RegistryError(f"{where}: comparison_level {comparison!r} is not a bin")
        if comparison in levels:
            raise RegistryError(f"{where}: comparison_level cannot be a treatment level")

    feasibility = dict(raw.get("feasibility") or {})
    reason = " ".join(str(raw.get("reason") or "").split())
    return AttributeSpec(
        name=name,
        type=kind,
        role=role,
        source=source,
        treatment=treatment,
        context=context,
        labels=labels,
        edges=edges,
        values=values,
        treatment_levels=levels,
        comparison_level=comparison,
        feasibility=feasibility,
        reason=reason,
    )


def load_registry(config: dict[str, Any]) -> AttributeRegistry:
    """Load and validate the registry from ``config["attributes"]``."""

    raw_attributes = config.get("attributes")
    if not isinstance(raw_attributes, dict) or not raw_attributes:
        raise RegistryError("config.attributes must be a non-empty mapping")
    specs = {name: _spec(str(name), raw) for name, raw in raw_attributes.items()}
    if not any(spec.treatment for spec in specs.values()):
        raise RegistryError("registry needs at least one treatment attribute")
    if not any(spec.context for spec in specs.values()):
        raise RegistryError("registry needs at least one context attribute")
    return AttributeRegistry(specs=specs)


def z_for_level(level: float) -> float:
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    return float(norm.ppf(1 - (1 - level) / 2))


def minimum_detectable_effect(
    n: int,
    alpha: float,
    *,
    power: float = 0.80,
    discordance: float = 0.25,
) -> float:
    """Planning MDE for a paired net-flip rate.

    ``MDE = (z_{1-alpha/2} + z_{power}) * sqrt(d / n)`` where ``d`` is the
    assumed share of discordant pairs. This is the standard normal-approximation
    sample-size relation for a paired difference, stated before the search and
    used only to report what a cell of this size could detect. It is not a
    post-hoc power claim.
    """

    if n <= 0:
        return 1.0
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    if not 0 < discordance <= 1:
        raise ValueError("discordance must be between 0 and 1")
    z_alpha = float(norm.ppf(1 - alpha / 2))
    z_power = float(norm.ppf(power))
    return min(1.0, (z_alpha + z_power) * float(np.sqrt(discordance / n)))
