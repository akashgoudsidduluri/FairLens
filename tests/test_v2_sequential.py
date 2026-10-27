"""R2 sequential stopping tests: the rule and a fixed-sample comparison."""

from __future__ import annotations

import pytest

from auditor.prober import Prober
from auditor.statistician import (
    SEQ_CONTINUE,
    SEQ_MATERIAL_HARM,
    SEQ_MAX_PAIRS,
    SEQ_NO_MATERIAL_HARM,
    running_net_flip_ci,
    sequential_stopping_decision,
)
from config_loader import load_config
from sandbox.generator import generate_segment
from schemas import ModelResponse


def test_sequential_rule_continues_before_min_pairs():
    decision = sequential_stopping_decision(
        20, 0, 20, materiality=0.02, min_pairs=100, max_pairs=1000
    )
    assert decision["action"] == SEQ_CONTINUE
    assert "min_pairs" in decision["reason"]


def test_sequential_rule_stops_when_interval_is_above_materiality():
    decision = sequential_stopping_decision(
        100, 0, 1000, materiality=0.02, min_pairs=100, max_pairs=2000
    )
    low, high = running_net_flip_ci(100, 0, 1000)
    assert low > 0.02
    assert decision["action"] == SEQ_MATERIAL_HARM
    assert decision["ci_low"] == low
    assert decision["ci_high"] == high


def test_sequential_rule_stops_when_interval_is_below_materiality():
    decision = sequential_stopping_decision(
        0, 0, 1000, materiality=0.02, min_pairs=100, max_pairs=2000
    )
    assert decision["action"] == SEQ_NO_MATERIAL_HARM
    assert decision["ci_high"] < 0.02


def test_sequential_rule_continues_while_interval_contains_materiality():
    decision = sequential_stopping_decision(
        20, 10, 1000, materiality=0.02, min_pairs=100, max_pairs=2000
    )
    assert decision["ci_low"] < 0.02 < decision["ci_high"]
    assert decision["action"] == SEQ_CONTINUE


def test_sequential_rule_stops_at_max_pairs():
    decision = sequential_stopping_decision(
        40, 40, 2000, materiality=0.02, min_pairs=100, max_pairs=2000
    )
    assert decision["action"] == SEQ_MAX_PAIRS


def test_sequential_rule_rejects_bad_parameters():
    with pytest.raises(ValueError):
        sequential_stopping_decision(
            1, 1, 2, materiality=0.0, min_pairs=10, max_pairs=20
        )
    with pytest.raises(ValueError):
        sequential_stopping_decision(
            1, 1, 2, materiality=0.02, min_pairs=30, max_pairs=20
        )


def _config(*, enabled: bool, min_pairs: int = 100, check_every: int = 50) -> dict:
    config = load_config()
    config["audit"]["sequential"] = {
        "enabled": enabled,
        "min_pairs": min_pairs,
        "check_every": check_every,
    }
    return config


def _prober(config: dict, *, twins_approved: bool) -> Prober:
    prober = Prober("http://example.test", config)
    originals, _ = generate_segment(1000, seed=101, gender="male")

    def sample(n, seed, attribute, target_group, comparison_group):
        return list(originals[:n])

    async def score_many(model_id, applicants):
        half = len(applicants) // 2
        responses: list[ModelResponse] = []
        for index in range(len(applicants)):
            approved = (index >= half) if twins_approved else (index < half)
            responses.append(
                ModelResponse(
                    approved=approved,
                    score=600.0 if approved else 400.0,
                )
            )
        return responses

    prober._sample_eligible = sample  # type: ignore[method-assign]
    prober._score_many = score_many  # type: ignore[method-assign]
    return prober


async def test_sequential_run_stops_early_while_fixed_run_uses_all_pairs():
    sequential = _prober(_config(enabled=True), twins_approved=False)
    fixed = _prober(_config(enabled=False), twins_approved=False)

    early = await sequential.probe_attribute(
        model_id=2,
        attribute="gender",
        target_group="female",
        comparison_group="male",
        n=1000,
        seed=42,
    )
    full = await fixed.probe_attribute(
        model_id=2,
        attribute="gender",
        target_group="female",
        comparison_group="male",
        n=1000,
        seed=42,
    )

    assert early.stopped_early is True
    assert early.stop_reason == SEQ_MATERIAL_HARM
    assert early.n == 100
    assert early.requested_n == 1000
    assert (early.b, early.c) == (100, 0)

    assert full.stopped_early is False
    assert full.stop_reason is None
    assert full.n == 1000
    assert (full.b, full.c) == (1000, 0)

    assert early.n < full.n
    assert early.b / early.n == full.b / full.n == 1.0


async def test_sequential_run_can_stop_for_no_material_harm():
    prober = _prober(_config(enabled=True), twins_approved=True)
    result = await prober.probe_attribute(
        model_id=2,
        attribute="gender",
        target_group="female",
        comparison_group="male",
        n=1000,
        seed=42,
    )
    assert result.stopped_early is True
    assert result.stop_reason == SEQ_NO_MATERIAL_HARM
    assert result.n == 100
    assert (result.b, result.c) == (0, 100)


async def test_sequential_does_not_stop_before_min_pairs():
    prober = _prober(
        _config(enabled=True, min_pairs=100, check_every=50),
        twins_approved=False,
    )
    result = await prober.probe_attribute(
        model_id=2,
        attribute="gender",
        target_group="female",
        comparison_group="male",
        n=1000,
        seed=42,
    )
    assert result.stop_reason == SEQ_MATERIAL_HARM
    assert result.n == 100


def test_sequential_config_is_preregistered_and_off_by_default():
    config = load_config()
    sequential = config["audit"]["sequential"]
    assert sequential["enabled"] is False
    assert sequential["min_pairs"] == 1000
    assert sequential["check_every"] == 200
    assert config["targets"]["probe_cap"] == 100000
