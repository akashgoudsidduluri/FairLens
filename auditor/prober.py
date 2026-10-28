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
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import numpy as np

from auditor.statistician import (
    SEQ_MATERIAL_HARM,
    SEQ_NO_MATERIAL_HARM,
    running_net_flip_ci,
    sequential_stopping_decision,
)
from sandbox.generator import (
    generate_applicants,
    generate_segment,
    income_band_boundaries,
    make_twin,
)
from schemas import AgentEvent, Applicant, ModelResponse, ProbeEvent
from targets.base import TargetAdapter, TargetError

ATTR_LABELS = {
    "gender": "gender",
    "pincode_group": "pincode group",
    "name_group": "name group",
}

PairEventSink = Callable[[list[ProbeEvent]], None]


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
    requested_n: int | None = None
    stopped_early: bool = False
    stop_reason: str | None = None


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
    def __init__(
        self,
        api_url: str,
        config: dict[str, Any],
        pair_event_sink: PairEventSink | None = None,
        target: TargetAdapter | None = None,
        sequential: bool | None = None,
    ) -> None:
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
        self.pair_event_sink = pair_event_sink
        self.pair_event_batch_size = max(
            1, int(config.get("api", {}).get("probe_event_batch_size", 25))
        )
        self.target = target
        self.sequential = sequential
        if target is not None:
            self.api_url = str(getattr(target, "base_url", self.api_url)).rstrip("/")
            target.reset()
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
        if self.target is not None:
            # Adapters own rate limiting and the per-audit probe cap. Call them
            # sequentially so those controls see one request at a time.
            flat: list[ModelResponse] = []
            try:
                for chunk in chunks:
                    flat.extend(await self.target.score_batch(chunk))
            except TargetError as exc:
                raise ProberError(str(exc)) from exc
            return flat
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
        if self.target is not None:
            try:
                data = await self.target.health()
            except Exception as exc:  # noqa: BLE001
                raise ProberError(
                    f"Target {self.target.name!r} is unreachable at "
                    f"{self.api_url}. Details: {type(exc).__name__}: {exc}"
                ) from exc
            if data.get("status") != "ok":
                raise ProberError(f"Target health check failed: {data}")
            self._emit(
                "prober",
                f"Target {self.target.name} reachable at {self.api_url}",
                {"api_url": self.api_url, "target": self.target.name},
            )
            return data
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
            f"(see README) and try again. Details: "
            f"{type(last_error).__name__}: {last_error}"
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
        if self.target is None:
            return originals, twins

        kept_originals: list[Applicant] = []
        kept_twins: list[Applicant] = []
        rejected: list[dict[str, str]] = []
        for original, twin in zip(originals, twins):
            feasible, reason = self.target.validate_pair(original, twin, attribute)
            if feasible:
                kept_originals.append(original)
                kept_twins.append(twin)
            else:
                rejected.append({"pair_id": original.id, "reason": reason})
        if rejected:
            examples = "; ".join(
                item["reason"] for item in rejected[:3] if item["reason"]
            )
            self._emit(
                "prober",
                f"Feasibility check rejected {len(rejected)} of {len(originals)} "
                f"{ATTR_LABELS[attribute]} twins outside the target's training "
                f"domain: {examples}",
                {
                    "attribute": attribute,
                    "requested_n": len(originals),
                    "feasible_n": len(kept_originals),
                    "rejected_n": len(rejected),
                    "rejected": rejected,
                },
            )
        return kept_originals, kept_twins

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

    # ---------------------------------------------------------- probe events
    @staticmethod
    def _summary(applicant: Applicant) -> dict[str, Any]:
        return {
            "id": applicant.id,
            "gender": applicant.gender,
            "age_band": applicant.age_band,
            "urban_rural": applicant.urban_rural,
            "pincode_group": applicant.pincode_group,
            "name_group": applicant.name_group,
            "income": applicant.income,
        }

    def _emit_pair_events(
        self,
        *,
        probe_id: str,
        phase: str,
        changed_field: str,
        originals: list[Applicant],
        twins: list[Applicant],
        original_responses: list[ModelResponse],
        twin_responses: list[ModelResponse],
        start_b: int = 0,
        start_c: int = 0,
        pair_offset: int = 0,
    ) -> None:
        """Emit one lightweight event per pair, in sink-sized batches.

        The running b/c counts restart at each probe (single attribute, cell, or
        matched re-test). The interval is the cheap normal approximation in
        ``running_net_flip_ci``; the final report still uses the bootstrap.
        Sequential probes pass ``start_b``/``start_c``/``pair_offset`` so a new
        chunk continues the same running stream.
        """

        if self.pair_event_sink is None:
            return
        level = float(self.config["audit"]["ci_level"])
        batch: list[ProbeEvent] = []
        b, c = start_b, start_c
        for local_index, (original, twin, o_resp, t_resp) in enumerate(
            zip(originals, twins, original_responses, twin_responses)
        ):
            index = pair_offset + local_index
            if o_resp.approved and not t_resp.approved:
                b += 1
            elif not o_resp.approved and t_resp.approved:
                c += 1
            n = index + 1
            low, high = running_net_flip_ci(b, c, n, level)
            batch.append(
                ProbeEvent(
                    probe_id=probe_id,
                    phase=phase,  # type: ignore[arg-type]
                    pair_index=index,
                    changed_field=changed_field,
                    original=self._summary(original),
                    twin=self._summary(twin),
                    original_approved=bool(o_resp.approved),
                    twin_approved=bool(t_resp.approved),
                    b_running=b,
                    c_running=c,
                    n_running=n,
                    net_flip_rate_running=(b - c) / n,
                    ci_low_running=low,
                    ci_high_running=high,
                )
            )
            if len(batch) >= self.pair_event_batch_size:
                self.pair_event_sink(batch)
                batch = []
        if batch:
            self.pair_event_sink(batch)

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

    async def _probe_attribute_sequential(
        self,
        *,
        model_id: int,
        attribute: str,
        target_group: str,
        comparison_group: str,
        originals: list[Applicant],
        twins: list[Applicant],
        n: int,
        seed: int,
    ) -> ProbeResult:
        cfg = self.config.get("audit", {}).get("sequential", {})
        check_every = max(1, int(cfg.get("check_every", 200)))
        min_pairs = max(1, int(cfg.get("min_pairs", 1000)))
        level = float(self.config["audit"]["ci_level"])
        materiality = float(self.config["audit"]["materiality"])

        b = c = 0
        done = 0
        decision: dict[str, Any] = {"action": "continue", "reason": ""}
        for start in range(0, n, check_every):
            end = min(n, start + check_every)
            o_resp, t_resp = await self._paired_score(
                model_id, originals[start:end], twins[start:end]
            )
            chunk_b, chunk_c = self._counts(o_resp, t_resp)
            self._emit_pair_events(
                probe_id=f"single-{attribute}-{target_group}",
                phase="single_attribute",
                changed_field=attribute,
                originals=originals[start:end],
                twins=twins[start:end],
                original_responses=o_resp,
                twin_responses=t_resp,
                start_b=b,
                start_c=c,
                pair_offset=done,
            )
            b += chunk_b
            c += chunk_c
            done = end
            decision = sequential_stopping_decision(
                b,
                c,
                done,
                materiality=materiality,
                min_pairs=min_pairs,
                max_pairs=n,
                level=level,
            )
            if decision["action"] != "continue":
                break

        stopped_early = (
            done < n
            and decision["action"] in {SEQ_MATERIAL_HARM, SEQ_NO_MATERIAL_HARM}
        )
        net = (b - c) / done if done else 0.0
        self._emit(
            "prober",
            f"Sequential {ATTR_LABELS[attribute]} {comparison_group}→{target_group}: "
            f"{done}/{n} twins, b={b}, c={c}, net={net:+.3f}, "
            f"{'stopped' if stopped_early else 'continued'} "
            f"({decision.get('reason', '')})",
            {
                "attribute": attribute,
                "target_group": target_group,
                "comparison_group": comparison_group,
                "n": done,
                "requested_n": n,
                "b": b,
                "c": c,
                "net_flip_rate": net,
                "sequential": True,
                "stopped_early": stopped_early,
                "stop_reason": decision["action"],
                "stopping": decision,
            },
        )
        return ProbeResult(
            attribute=attribute,
            target_group=target_group,
            comparison_group=comparison_group,
            n=done,
            b=b,
            c=c,
            seed=seed,
            requested_n=n,
            stopped_early=stopped_early,
            stop_reason=str(decision["action"]),
        )

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
        requested_n = n
        originals = self._sample_eligible(
            n, seed, attribute, target_group, comparison_group
        )
        originals, twins = self._build_pairs(originals, attribute, target_group, seed)
        n = len(originals)
        if n == 0:
            raise ProberError(
                f"No feasible {attribute} twins for target "
                f"{getattr(self.target, 'name', self.api_url)!r}"
            )
        use_sequential = self.sequential
        if use_sequential is None:
            use_sequential = bool(
                self.config.get("audit", {}).get("sequential", {}).get(
                    "enabled", False
                )
            )
        if use_sequential:
            return await self._probe_attribute_sequential(
                model_id=model_id,
                attribute=attribute,
                target_group=target_group,
                comparison_group=comparison_group,
                originals=originals,
                twins=twins,
                n=n,
                seed=seed,
            )
        o_resp, t_resp = await self._paired_score(model_id, originals, twins)
        b, c = self._counts(o_resp, t_resp)
        self._emit_pair_events(
            probe_id=f"single-{attribute}-{target_group}",
            phase="single_attribute",
            changed_field=attribute,
            originals=originals,
            twins=twins,
            original_responses=o_resp,
            twin_responses=t_resp,
        )
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
            requested_n=requested_n,
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
            self._emit_pair_events(
                probe_id=f"{g}|{age}|{urban}",
                phase="intersectional",
                changed_field="gender",
                originals=all_originals[start:end],
                twins=all_twins[start:end],
                original_responses=o_resp[start:end],
                twin_responses=t_resp[start:end],
            )
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
        requested_n = n
        n = len(originals)
        if n == 0:
            raise ProberError(
                f"No feasible matched {attribute} twins for target "
                f"{getattr(self.target, 'name', self.api_url)!r}"
            )
        o_resp, t_resp = await self._paired_score(model_id, originals, twins)
        b, c = self._counts(o_resp, t_resp)
        self._emit_pair_events(
            probe_id=f"matched-{attribute}-{target_group}",
            phase="matched_retest",
            changed_field=attribute,
            originals=originals,
            twins=twins,
            original_responses=o_resp,
            twin_responses=t_resp,
        )

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
            requested_n=requested_n,
        )

    # ---------------------------------------------------------------- sync API
    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def check_health_sync(self) -> dict[str, Any]:
        return self._run(self.check_health())

    def score_many_sync(
        self, model_id: int, applicants: list[Applicant]
    ) -> list[ModelResponse]:
        return self._run(self._score_many(model_id, applicants))

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
