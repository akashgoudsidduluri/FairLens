"""Black-box prober.

The auditor only sends applicants to the sandbox over HTTP. It never imports
the scoring code. Requests are batched, retried, and timed out according to
config.yaml.

Twin construction flips exactly one signal:
- gender (name changes too, within the same synthetic name group)
- pincode_group (pincode from another group with the same urban/rural tag)
- name_group (name from another group with the same gender)
- intersectional cells use gender flips inside gender x age band x urban/rural.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import numpy as np

from sandbox.generator import (
    generate_applicants,
    generate_segment,
    income_band_boundaries,
    make_twin,
)
from schemas import AgentEvent, Applicant, ModelResponse

ATTR_LABELS = {
    "gender": "gender",
    "pincode_group": "pincode group",
    "name_group": "name group",
}


class ProberError(RuntimeError):
    """Raised for unreachable or invalid sandbox APIs."""


@dataclass
class ProbeResult:
    attribute: str
    target_group: str
    comparison_group: str
    n: int
    b: int
    c: int
    seed: int
    bands: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CellProbe:
    target_gender: str
    comparison_gender: str
    age_band: str
    urban_rural: str
    n: int
    b: int
    c: int


class Prober:
    def __init__(self, api_url: str, config: dict[str, Any]) -> None:
        url = (api_url or "").strip().rstrip("/")
        if not url:
            raise ProberError("API URL is empty")
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ProberError(f"Invalid API URL: {api_url!r}")
        self.api_url = url
        self.config = config
        self.batch_size = int(config["api"]["batch_size"])
        self.timeout = float(config["api"]["timeout_seconds"])
        self.retries = int(config["api"]["retries"])
        self.events: list[AgentEvent] = []

    # ------------------------------------------------------------------ events
    def _emit(self, agent: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append(AgentEvent(agent=agent, message=message, payload=payload or {}))

    def drain_events(self) -> list[AgentEvent]:
        events = list(self.events)
        self.events.clear()
        return events

    # -------------------------------------------------------------------- HTTP
    async def _score_chunk(
        self, client: httpx.AsyncClient, model_id: int, applicants: list[Applicant]
    ) -> list[ModelResponse]:
        payload = [a.model_dump(mode="json") for a in applicants]
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await client.post(
                    f"{self.api_url}/score_batch",
                    params={"model": model_id},
                    json=payload,
                )
                if response.status_code >= 500:
                    raise ProberError(
                        f"Sandbox returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    raise ProberError(
                        f"Sandbox rejected the request (HTTP {response.status_code}): "
                        f"{response.text[:200]}"
                    )
                data = response.json()
                if not isinstance(data, list) or len(data) != len(payload):
                    raise ProberError(
                        "Sandbox returned a malformed batch "
                        f"({len(data) if isinstance(data, list) else 'non-list'} vs {len(payload)})"
                    )
                return [ModelResponse.model_validate(item) for item in data]
            except ProberError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(0.25 * (2**attempt))
        raise ProberError(
            f"Could not reach sandbox at {self.api_url} after {self.retries + 1} attempts: "
            f"{last_error}"
        )

    async def _score_many(
        self, model_id: int, applicants: list[Applicant]
    ) -> list[ModelResponse]:
        if not applicants:
            return []
        chunks = [
            applicants[i : i + self.batch_size]
            for i in range(0, len(applicants), self.batch_size)
        ]
        semaphore = asyncio.Semaphore(4)
        async with httpx.AsyncClient(timeout=self.timeout) as client:

            async def run(chunk: list[Applicant]) -> list[ModelResponse]:
                async with semaphore:
                    return await self._score_chunk(client, model_id, chunk)

            results = await asyncio.gather(*(run(chunk) for chunk in chunks))
        flat: list[ModelResponse] = []
        for part in results:
            flat.extend(part)
        return flat

    async def check_health(self) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=min(self.timeout, 5.0)) as client:
                    response = await client.get(f"{self.api_url}/health")
                    response.raise_for_status()
                    data = response.json()
                    if data.get("status") != "ok":
                        raise ProberError(f"Sandbox health check failed: {data}")
                    self._emit(
                        "prober",
                        f"Sandbox reachable at {self.api_url} ({data.get('models', '?')} models)",
                        {"api_url": self.api_url},
                    )
                    return data
            except ProberError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self.retries:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise ProberError(
            f"Sandbox is unreachable at {self.api_url}. Start the sandbox API "
            f"(see README) and try again. Details: {last_error}"
        )

    # --------------------------------------------------------------- sampling
    def _eligible(
        self,
        applicant: Applicant,
        attribute: str,
        target_group: str,
        comparison_group: str,
    ) -> bool:
        if attribute == "gender":
            return applicant.gender == comparison_group
        if attribute == "pincode_group":
            return applicant.pincode_group == comparison_group
        if attribute == "name_group":
            return applicant.name_group == comparison_group
        return False

    def _sample_eligible(
        self,
        n: int,
        seed: int,
        attribute: str,
        target_group: str,
        comparison_group: str,
    ) -> list[Applicant]:
        rng = np.random.default_rng(seed)
        collected: list[Applicant] = []
        attempts = 5
        per_attempt = max(n * 2, 1000)
        for attempt in range(attempts):
            pool, _ = generate_applicants(per_attempt, seed=seed + attempt * 7919)
            eligible = [
                a
                for a in pool
                if self._eligible(a, attribute, target_group, comparison_group)
            ]
            rng.shuffle(eligible)
            collected.extend(eligible)
            if len(collected) >= n:
                break
        if len(collected) < n:
            raise ProberError(
                f"Not enough comparison-group applicants for {attribute}: "
                f"needed {n}, found {len(collected)}"
            )
        return collected[:n]

    def _build_pairs(
        self,
        originals: list[Applicant],
        attribute: str,
        target_group: str,
        seed: int,
    ) -> tuple[list[Applicant], list[Applicant]]:
        rng = np.random.default_rng(seed + 101)
        twins = [
            make_twin(original, attribute, target_group, rng) for original in originals
        ]
        return originals, twins

    async def _paired_score(
        self, model_id: int, originals: list[Applicant], twins: list[Applicant]
    ) -> tuple[list[ModelResponse], list[ModelResponse]]:
        combined = list(originals) + list(twins)
        responses = await self._score_many(model_id, combined)
        return responses[: len(originals)], responses[len(originals) :]

    @staticmethod
    def _counts(
        originals: list[ModelResponse], twins: list[ModelResponse]
    ) -> tuple[int, int]:
        b = sum(1 for o, t in zip(originals, twins) if o.approved and not t.approved)
        c = sum(1 for o, t in zip(originals, twins) if not o.approved and t.approved)
        return b, c

    # ----------------------------------------------------------- public probes
    async def sample_observational(
        self, model_id: int, n: int, seed: int
    ) -> tuple[list[Applicant], list[ModelResponse]]:
        applicants, _ = generate_applicants(n, seed=seed)
        responses = await self._score_many(model_id, applicants)
        approved = sum(r.approved for r in responses)
        self._emit(
            "prober",
            f"Drew {n} natural-population applicants; observed {approved / n:.1%} approvals",
            {"n": n, "approval_rate": approved / n},
        )
        return applicants, responses

    async def probe_attribute(
        self,
        model_id: int,
        attribute: str,
        target_group: str,
        comparison_group: str,
        n: int,
        seed: int,
    ) -> ProbeResult:
        if attribute not in ATTR_LABELS:
            raise ValueError(f"unsupported attribute: {attribute}")
        originals = self._sample_eligible(
            n, seed, attribute, target_group, comparison_group
        )
        originals, twins = self._build_pairs(originals, attribute, target_group, seed)
        o_resp, t_resp = await self._paired_score(model_id, originals, twins)
        b, c = self._counts(o_resp, t_resp)
        net = (b - c) / n
        self._emit(
            "prober",
            f"Flipped {ATTR_LABELS[attribute]} {comparison_group}→{target_group}: "
            f"{n} twins, b={b}, c={c}, net={net:+.3f}",
            {
                "attribute": attribute,
                "target_group": target_group,
                "comparison_group": comparison_group,
                "n": n,
                "b": b,
                "c": c,
                "net_flip_rate": net,
            },
        )
        return ProbeResult(
            attribute=attribute,
            target_group=target_group,
            comparison_group=comparison_group,
            n=n,
            b=b,
            c=c,
            seed=seed,
        )

    async def probe_intersectional(
        self, model_id: int, n_per_cell: int, seed: int
    ) -> list[CellProbe]:
        cells: list[CellProbe] = []
        all_originals: list[Applicant] = []
        all_twins: list[Applicant] = []
        cell_slices: list[tuple[int, int, str, str, str, str]] = []

        cell_index = 0
        for target_gender in ("female", "male"):
            comparison_gender = "male" if target_gender == "female" else "female"
            for age_band in ("<35", "35-44", "45+"):
                for urban_rural in ("urban", "rural"):
                    original_pool, _ = generate_segment(
                        n_per_cell,
                        seed=seed + 13_000 + cell_index * 97,
                        gender=comparison_gender,
                        age_band=age_band,
                        urban_rural=urban_rural,
                    )
                    rng = np.random.default_rng(seed + 17_000 + cell_index)
                    rng.shuffle(original_pool)
                    originals = original_pool[:n_per_cell]
                    twins = [
                        make_twin(o, "gender", target_gender, rng) for o in originals
                    ]
                    start = len(all_originals)
                    all_originals.extend(originals)
                    all_twins.extend(twins)
                    cell_slices.append(
                        (
                            start,
                            start + len(originals),
                            target_gender,
                            comparison_gender,
                            age_band,
                            urban_rural,
                        )
                    )
                    cell_index += 1

        o_resp, t_resp = await self._paired_score(model_id, all_originals, all_twins)
        for start, end, g, other, age, urban in cell_slices:
            b, c = self._counts(o_resp[start:end], t_resp[start:end])
            cells.append(
                CellProbe(
                    target_gender=g,
                    comparison_gender=other,
                    age_band=age,
                    urban_rural=urban,
                    n=end - start,
                    b=b,
                    c=c,
                )
            )
        self._emit(
            "prober",
            f"Scanned {len(cells)} intersectional cells with {n_per_cell} twins each "
            f"({len(all_originals)} pairs)",
            {"cells": len(cells), "pairs": len(all_originals)},
        )
        return cells

    async def matched_retest(
        self,
        model_id: int,
        attribute: str,
        target_group: str,
        comparison_group: str,
        n: int,
        seed: int,
        *,
        age_band: str | None = None,
        urban_rural: str | None = None,
    ) -> ProbeResult:
        """Re-run twins inside income quintiles of the comparison group."""

        if attribute == "gender":
            originals, _ = generate_segment(
                n,
                seed=seed + 29_000,
                gender=comparison_group,
                age_band=age_band,
                urban_rural=urban_rural,
            )
        elif attribute == "pincode_group":
            originals, _ = generate_segment(
                n,
                seed=seed + 29_000,
                pincode_group=comparison_group,
                age_band=age_band,
                urban_rural=urban_rural,
            )
        elif attribute == "name_group":
            originals, _ = generate_segment(
                n,
                seed=seed + 29_000,
                name_group=comparison_group,
                age_band=age_band,
                urban_rural=urban_rural,
            )
        else:
            raise ValueError(f"unsupported attribute: {attribute}")

        originals, twins = self._build_pairs(originals, attribute, target_group, seed + 5)
        o_resp, t_resp = await self._paired_score(model_id, originals, twins)
        b, c = self._counts(o_resp, t_resp)

        boundaries = income_band_boundaries(
            [a.income for a in originals], int(self.config["audit"]["income_bands"])
        )
        bands: list[dict[str, Any]] = []
        for band_index in range(int(self.config["audit"]["income_bands"])):
            idx = [
                i
                for i, a in enumerate(originals)
                if _band_of(a.income, boundaries) == band_index
            ]
            if not idx:
                continue
            bb = sum(1 for i in idx if o_resp[i].approved and not t_resp[i].approved)
            cc = sum(1 for i in idx if not o_resp[i].approved and t_resp[i].approved)
            bands.append(
                {
                    "band": band_index,
                    "n": len(idx),
                    "b": bb,
                    "c": cc,
                    "net_flip_rate": (bb - cc) / len(idx),
                }
            )
        net = (b - c) / n
        self._emit(
            "prober",
            f"Income-matched re-test ({attribute} {comparison_group}→{target_group}): "
            f"{n} twins across {len(bands)} income bands, net={net:+.3f}",
            {"n": n, "b": b, "c": c, "bands": bands},
        )
        return ProbeResult(
            attribute=attribute,
            target_group=target_group,
            comparison_group=comparison_group,
            n=n,
            b=b,
            c=c,
            seed=seed + 29_000,
            bands=bands,
        )

    # ---------------------------------------------------------------- sync API
    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def check_health_sync(self) -> dict[str, Any]:
        return self._run(self.check_health())

    def sample_observational_sync(
        self, model_id: int, n: int, seed: int
    ) -> tuple[list[Applicant], list[ModelResponse]]:
        return self._run(self.sample_observational(model_id, n, seed))

    def probe_attribute_sync(self, **kwargs: Any) -> ProbeResult:
        return self._run(self.probe_attribute(**kwargs))

    def probe_intersectional_sync(
        self, model_id: int, n_per_cell: int, seed: int
    ) -> list[CellProbe]:
        return self._run(self.probe_intersectional(model_id, n_per_cell, seed))

    def matched_retest_sync(self, **kwargs: Any) -> ProbeResult:
        return self._run(self.matched_retest(**kwargs))


def _band_of(value: float, boundaries: list[float]) -> int:
    return int(np.searchsorted(boundaries, value, side="right"))
