"""R3c tests: LLM parsing, caching, variance, caps, twins, unavailable state."""

from __future__ import annotations

import json

import numpy as np
import pytest

from config_loader import load_config
from sandbox.generator import generate_segment, make_twin
from targets import build_target
from targets.llm.adapter import (
    LLMCapExceeded,
    LLMTargetAdapter,
    LLMUnavailable,
    LLMUnparseable,
    ScreenResult,
    build_llm_target,
)
from targets.llm.cache import ResponseCache, prompt_key
from targets.llm.client import Completion
from targets.llm.parsing import ParseFailure, ScreenDecision, parse_response
from targets.llm.prompt import build_prompt, diff_fields
from targets.llm.variance import (
    applicant_disagreement,
    pair_flip_series,
    pair_variance,
    summarize_variance,
)


class FakeClient:
    """Test double for the CompletionClient protocol. Not used in product code."""

    model = "fake-model"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> Completion:
        self.prompts.append(prompt)
        reply = self.replies[self.calls % len(self.replies)]
        self.calls += 1
        return Completion(text=reply, input_tokens=120, output_tokens=20)


def _adapter(tmp_path, replies: list[str], **overrides) -> tuple[LLMTargetAdapter, FakeClient]:
    spec = dict(load_config()["llm"])
    spec["cache_dir"] = str(tmp_path / "cache")
    spec.update(overrides)
    client = FakeClient(replies)
    adapter = LLMTargetAdapter(
        spec,
        client=client,
        model="fake-model",
        cache=ResponseCache(spec["cache_dir"]),
    )
    return adapter, client


def _applicant(seed: int = 1):
    people, _ = generate_segment(1, seed=seed, gender="female")
    return people[0]


# --------------------------------------------------------------------- parsing
@pytest.mark.parametrize(
    "text",
    [
        '{"approved": true, "score": 720}',
        '{"approved": false, "score": 0}',
        '{"approved": true, "score": 1000}',
        '  {"score": 510.5, "approved": false}  ',
    ],
)
def test_strict_parser_accepts_the_contract(text):
    decision = parse_response(text)
    assert isinstance(decision, ScreenDecision)
    assert isinstance(decision.approved, bool)
    assert 0 <= decision.score <= 1000


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("", "empty"),
        ("Approved. Score 800.", "not valid JSON"),
        ('```json\n{"approved": true, "score": 800}\n```', "not valid JSON"),
        ('{"approved": true}', "exactly the keys"),
        ('{"approved": true, "score": 800, "why": "ok"}', "exactly the keys"),
        ('{"approved": "yes", "score": 800}', "boolean"),
        ('{"approved": 1, "score": 800}', "boolean"),
        ('{"approved": true, "score": "800"}', "number"),
        ('{"approved": true, "score": true}', "number"),
        ('{"approved": true, "score": 1001}', "outside 0..1000"),
        ('{"approved": true, "score": -1}', "outside 0..1000"),
        ('{"approved": true, "score": NaN}', "not valid JSON"),
        ("[true, 800]", "JSON object"),
    ],
)
def test_strict_parser_rejects_everything_else(text, fragment):
    decision = parse_response(text)
    assert isinstance(decision, ParseFailure)
    assert fragment in decision.reason


# ----------------------------------------------------------------------- twins
def test_name_twin_changes_only_the_name_line():
    people, _ = generate_segment(4, seed=21, name_group="N1", gender="female")
    original = people[0]
    twin = make_twin(original, "name_group", "N2", np.random.default_rng(0))
    assert diff_fields(original, twin) == ["name"]

    left = build_prompt(original).splitlines()
    right = build_prompt(twin).splitlines()
    changed = [index for index, line in enumerate(left) if line != right[index]]
    assert len(changed) == 1
    assert left[changed[0]].startswith("Name:")

    adapter = _adapter_for_validation()
    feasible, reason = adapter.validate_pair(original, twin, "name_group")
    assert feasible, reason


def test_region_twin_changes_only_the_region_line():
    people, _ = generate_segment(4, seed=22, pincode_group="P1", urban_rural="urban")
    original = people[0]
    twin = make_twin(original, "pincode_group", "P2", np.random.default_rng(0))
    assert diff_fields(original, twin) == ["region"]

    left = build_prompt(original).splitlines()
    right = build_prompt(twin).splitlines()
    changed = [index for index, line in enumerate(left) if line != right[index]]
    assert len(changed) == 1
    assert left[changed[0]].startswith("Region:")

    adapter = _adapter_for_validation()
    feasible, reason = adapter.validate_pair(original, twin, "pincode_group")
    assert feasible, reason


def test_gender_twin_is_not_defined_for_the_llm_screener():
    people, _ = generate_segment(2, seed=23, gender="female")
    twin = make_twin(people[0], "gender", "male", np.random.default_rng(0))
    adapter = _adapter_for_validation()
    feasible, reason = adapter.validate_pair(people[0], twin, "gender")
    assert feasible is False
    assert "only names and regions" in reason


def _adapter_for_validation() -> LLMTargetAdapter:
    import tempfile
    from pathlib import Path

    temporary = tempfile.TemporaryDirectory(prefix="fairlens-llm-pair-")
    # Keep the directory alive for the process lifetime of the test.
    _KEEP.append(temporary)
    return LLMTargetAdapter(
        load_config()["llm"],
        client=FakeClient(['{"approved": true, "score": 500}']),
        model="fake-model",
        cache=ResponseCache(Path(temporary.name) / "cache"),
    )


_KEEP: list = []


# --------------------------------------------------------------- majority/cache
def test_majority_outcome_and_median_score(tmp_path):
    adapter, client = _adapter(
        tmp_path,
        [
            '{"approved": true, "score": 700}',
            '{"approved": false, "score": 100}',
            '{"approved": true, "score": 800}',
        ],
    )
    result = adapter.screen(_applicant())
    assert result.approvals == (True, False, True)
    assert result.majority is True
    assert result.score == 700
    assert result.valid_n == 3
    assert client.calls == 3
    assert adapter.probes_used == 3


def test_cache_hits_are_free_and_reproducible(tmp_path):
    replies = [
        '{"approved": true, "score": 700}',
        '{"approved": true, "score": 710}',
        '{"approved": true, "score": 720}',
    ]
    adapter, client = _adapter(tmp_path, replies)
    applicant = _applicant()
    first = adapter.screen(applicant)
    assert client.calls == 3
    assert adapter.cache_hits == 0
    assert adapter.probes_used == 3

    second = adapter.screen(applicant)
    assert second == first
    assert client.calls == 3
    assert adapter.cache_hits == 3
    assert adapter.probes_used == 3

    fresh_adapter, fresh_client = _adapter(tmp_path, replies)
    third = fresh_adapter.screen(applicant)
    assert third == first
    assert fresh_client.calls == 0
    assert fresh_adapter.cache_hits == 3


def test_prompt_hash_changes_with_prompt_and_temperature():
    base = prompt_key(model="m", prompt="p", temperature=0.0, max_tokens=64)
    assert base != prompt_key(
        model="m", prompt="p2", temperature=0.0, max_tokens=64
    )
    assert base != prompt_key(
        model="m", prompt="p", temperature=0.7, max_tokens=64
    )
    assert base == prompt_key(
        model="m", prompt="p", temperature=0.0, max_tokens=64
    )


# ------------------------------------------------------------------ parse fails
def test_one_unparseable_repeat_is_counted_but_majority_still_works(tmp_path):
    adapter, _ = _adapter(
        tmp_path,
        [
            "I cannot answer that.",
            '{"approved": true, "score": 600}',
            '{"approved": true, "score": 700}',
        ],
    )
    result = adapter.screen(_applicant())
    assert result.majority is True
    assert result.valid_n == 2
    assert adapter.parse_failures == 1
    assert len(result.errors) == 1


def test_too_few_parseable_repeats_is_unresolved_and_never_silent(tmp_path):
    adapter, _ = _adapter(
        tmp_path,
        [
            "not json",
            "also not json",
            '{"approved": true, "score": 600}',
        ],
    )
    applicant = _applicant()
    result = adapter.screen(applicant)
    assert result.majority is None
    assert result.valid_n == 1
    assert result.unresolved_reason.startswith("only 1 of 3")
    assert adapter.unresolved == 1
    assert adapter.parse_failures == 2

    with pytest.raises(LLMUnparseable):
        import asyncio

        asyncio.run(adapter.score_batch([applicant]))


# -------------------------------------------------------------------- variance
def test_pair_variance_and_applicant_disagreement():
    original = ScreenResult(
        prompt="p",
        approvals=(True, True, False),
        scores=(700.0, 710.0, 100.0),
        errors=(),
        majority=True,
        score=700.0,
        valid_n=3,
    )
    twin = ScreenResult(
        prompt="q",
        approvals=(False, False, False),
        scores=(100.0, 110.0, 120.0),
        errors=(),
        majority=False,
        score=110.0,
        valid_n=3,
    )
    series = pair_flip_series(original, twin)
    assert series == [True, True, False]
    assert pair_variance(series) == pytest.approx(1 / 3)
    assert applicant_disagreement(original) == pytest.approx(1 / 3)
    assert applicant_disagreement(twin) == 0.0

    summary = summarize_variance([(original, twin)])
    assert summary["pairs"] == 1
    assert summary["pairs_scored"] == 1
    assert summary["unresolved_pairs"] == 0
    assert summary["mean_pair_variance"] == pytest.approx(1 / 3)
    assert summary["pairs_with_repeat_disagreement"] == 1
    assert summary["share_pairs_with_repeat_disagreement"] == 1.0
    assert summary["mean_applicant_disagreement"] == pytest.approx(1 / 6)
    assert summary["mean_repeat_flip_rate"] == pytest.approx(2 / 3)


def test_unresolved_pairs_are_excluded_from_variance():
    original = ScreenResult("p", (True, None, True), (700.0, None, 700.0), (), True, 700.0, 2)
    twin = ScreenResult("q", (None, None, None), (None, None, None), (), None, None, 0, "none")
    summary = summarize_variance([(original, twin)])
    assert summary["pairs"] == 1
    assert summary["pairs_scored"] == 0
    assert summary["unresolved_pairs"] == 1
    assert summary["mean_pair_variance"] is None


# ------------------------------------------------------------------------ caps
def test_call_cap_is_enforced_before_the_third_call(tmp_path):
    adapter, client = _adapter(
        tmp_path,
        ['{"approved": true, "score": 700}'] * 3,
        max_calls_per_audit=2,
    )
    with pytest.raises(LLMCapExceeded):
        import asyncio

        asyncio.run(adapter.score_batch([_applicant()]))
    assert adapter.probes_used == 2
    assert client.calls == 2


def test_cost_cap_is_enforced_before_the_first_call(tmp_path):
    adapter, client = _adapter(
        tmp_path,
        ['{"approved": true, "score": 700}'],
        max_cost_usd=1e-9,
    )
    with pytest.raises(LLMCapExceeded):
        adapter.screen(_applicant())
    assert adapter.probes_used == 0
    assert client.calls == 0


# ------------------------------------------------------------------ availability
def test_missing_key_reports_unavailable_and_never_scores(tmp_path):
    config = load_config()
    env = {
        "ANTHROPIC_MODEL": "some-model",
        "FAIRLENS_LLM_CACHE": str(tmp_path / "cache"),
    }
    adapter = build_llm_target("llm:screener", config, env=env)
    assert adapter.available() is False
    assert adapter.model == "some-model"

    import asyncio

    health = asyncio.run(adapter.health())
    assert health["status"] == "unavailable"
    assert "ANTHROPIC_API_KEY" in health["reason"]

    with pytest.raises(LLMUnavailable):
        asyncio.run(adapter.score_batch([_applicant()]))


def test_build_target_dispatches_llm_and_applies_the_cap(tmp_path):
    config = load_config()
    env = {"FAIRLENS_LLM_CACHE": str(tmp_path / "cache")}
    adapter = build_target("llm:screener", config, env=env)
    assert isinstance(adapter, LLMTargetAdapter)
    assert adapter.name == "llm-screener"
    assert adapter.probe_cap == config["llm"]["max_calls_per_audit"]
    assert adapter.supported_probes == {"name_group", "pincode_group"}
    assert set(adapter.unsupported_details) == {"gender", "intersectional"}
    assert adapter.supports_mitigation is False


def test_cache_payload_is_strict_json_with_one_slot_per_repeat(tmp_path):
    adapter, _ = _adapter(tmp_path, ['{"approved": true, "score": 700}'])
    adapter.screen(_applicant())
    files = list((tmp_path / "cache").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["model"] == "fake-model"
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 64
    assert len(payload["samples"]) == 3
    assert "api_key" not in files[0].read_text(encoding="utf-8").lower()


def test_llm_evaluation_is_labelled_underpowered(tmp_path):
    from eval.run_llm_eval import evaluate

    adapter, _ = _adapter(
        tmp_path,
        ['{"approved": true, "score": 700}'],
        pairs_per_probe=2,
    )
    rows, budget = evaluate(adapter, load_config(), seed=5)
    assert len(rows) == 2
    assert {row["probe"] for row in rows} == {"name_group", "pincode_group"}
    assert all(row["pairs_requested"] == 2 for row in rows)
    assert all(row["pairs_scored"] == 2 for row in rows)
    assert all(row["b"] == 0 and row["c"] == 0 for row in rows)
    assert all("Underpowered" in row["verdict"] for row in rows)
    assert budget["api_calls"] == 24
    assert budget["max_calls"] == 300
    assert budget["cost_usd"] > 0
