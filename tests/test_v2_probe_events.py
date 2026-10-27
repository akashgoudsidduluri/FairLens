"""R1 probe event tests: one event per twin, batched, with running stats."""

from __future__ import annotations

import pytest

from auditor.prober import Prober
from auditor.statistician import running_net_flip_ci
from config_loader import load_config
from sandbox.generator import generate_segment
from schemas import ModelResponse


def test_running_ci_is_bounded_and_shrinks_with_n():
    low1, high1 = running_net_flip_ci(40, 0, 100)
    low2, high2 = running_net_flip_ci(400, 0, 1000)
    assert -1 <= low1 <= high1 <= 1
    assert -1 <= low2 <= high2 <= 1
    assert (high2 - low2) < (high1 - low1)
    assert low2 > low1


async def test_prober_emits_one_batched_event_per_pair():
    config = load_config()
    config["api"]["probe_event_batch_size"] = 3
    batches = []
    prober = Prober("http://example.test", config, pair_event_sink=batches.append)

    n = 7
    originals = generate_segment(n, seed=101, gender="male")[0]

    def sample(*args, **kwargs):
        return list(originals)

    async def fake_score(model_id, applicants):
        half = len(applicants) // 2
        return [
            ModelResponse(approved=index < half, score=600.0 if index < half else 400.0)
            for index in range(len(applicants))
        ]

    prober._sample_eligible = sample  # type: ignore[method-assign]
    prober._score_many = fake_score  # type: ignore[method-assign]

    result = await prober.probe_attribute(
        model_id=2,
        attribute="gender",
        target_group="female",
        comparison_group="male",
        n=n,
        seed=42,
    )

    assert (result.n, result.b, result.c) == (7, 7, 0)
    assert [len(batch) for batch in batches] == [3, 3, 1]
    events = [event for batch in batches for event in batch]
    assert len(events) == n
    assert [event.pair_index for event in events] == list(range(n))
    assert all(event.probe_id == "single-gender-female" for event in events)
    assert all(event.changed_field == "gender" for event in events)
    assert all(event.original["gender"] == "male" for event in events)
    assert all(event.twin["gender"] == "female" for event in events)
    assert all(event.original_approved for event in events)
    assert not any(event.twin_approved for event in events)

    last = events[-1]
    assert (last.b_running, last.c_running, last.n_running) == (7, 0, 7)
    assert last.net_flip_rate_running == 1.0
    assert last.ci_low_running <= last.net_flip_rate_running <= last.ci_high_running
    assert last.ci_method == "normal_approximation"
    assert last.timestamp.tzinfo is not None
