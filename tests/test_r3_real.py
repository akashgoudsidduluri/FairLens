"""R3a tests: dataset loading, mapping, feasibility, adapters, unsupported probes."""

from __future__ import annotations

import ast
import json

import httpx
import numpy as np
import pytest

from auditor.pipeline import collect_audit
from config_loader import REPO_ROOT, load_config
from sandbox.generator import generate_applicants, make_twin
from targets import build_target
from targets.real.datasets import dataset_summary, load_dataset
from targets.real.features import (
    ADULT_FEATURES,
    CREDIT_FEATURES,
    map_applicant,
    validate_pair,
    validate_row,
)
from targets.real.models import load_real_model
from targets.real.serve import app as real_app


@pytest.fixture(scope="module")
def transport():
    return httpx.ASGITransport(app=real_app)


@pytest.fixture(scope="module")
def applicants():
    people, _ = generate_applicants(40, seed=7)
    return people


def test_datasets_are_cached_with_expected_columns():
    credit = load_dataset("uci_credit_default")
    assert credit.shape == (30000, 24)
    assert {
        "limit_bal",
        "sex",
        "age",
        "pay_0",
        "pay_2",
        "bill_amt1",
        "pay_amt6",
        "target",
    } <= set(credit.columns)
    assert set(credit["sex"].unique()) == {1, 2}
    assert credit["target"].isin([0, 1]).all()

    adult = load_dataset("adult_income")
    assert adult.shape[0] == 32561
    assert {
        "age",
        "workclass",
        "education",
        "marital_status",
        "occupation",
        "race",
        "sex",
        "hours_per_week",
        "native_country",
        "target",
    } <= set(adult.columns)
    assert set(adult["sex"].unique()) == {"Male", "Female"}
    assert adult["target"].isin([0, 1]).all()


def test_dataset_summary_records_source_and_license():
    summary = dataset_summary("adult_income")
    assert summary["rows"] == 32561
    assert summary["license"] == "CC BY 4.0"
    assert "archive.ics.uci.edu" in summary["url"]
    assert len(summary["sha256"]) == 64
    assert summary["cache"].startswith("data/real/")


@pytest.mark.parametrize("model_name", ["uci_credit_default", "adult_income"])
def test_mapping_stays_inside_the_training_domain(model_name, applicants):
    model = load_real_model(model_name)
    features = CREDIT_FEATURES if model_name == "uci_credit_default" else ADULT_FEATURES
    for applicant in applicants[:10]:
        row = map_applicant(model_name, applicant, model.profile)
        assert list(row) == features
        assert validate_row(model_name, row, model.profile) == []
        assert set(model.metrics["used_canonical_fields"]) <= set(
            applicant.model_dump()
        )


def test_gender_twin_changes_exactly_sex():
    from sandbox.generator import generate_segment

    people, _ = generate_segment(10, seed=11, gender="male")
    model = load_real_model("adult_income")
    original = people[0]
    twin = make_twin(original, "gender", "female", np.random.default_rng(0))
    left = map_applicant("adult_income", original, model.profile)
    right = map_applicant("adult_income", twin, model.profile)
    changed = [key for key in left if left[key] != right[key]]
    assert changed == ["sex"]
    feasible, reason = validate_pair(
        "adult_income", original, twin, "gender", model.profile
    )
    assert feasible, reason


def test_pincode_twin_is_rejected_because_no_feature_changes():
    from sandbox.generator import generate_segment

    people, _ = generate_segment(5, seed=12, pincode_group="P1")
    model = load_real_model("uci_credit_default")
    original = people[0]
    twin = make_twin(original, "pincode_group", "P2", np.random.default_rng(0))
    feasible, reason = validate_pair(
        "uci_credit_default", original, twin, "pincode_group", model.profile
    )
    assert feasible is False
    assert "changed no mapped feature" in reason


def test_out_of_range_mapping_is_rejected():
    model = load_real_model("uci_credit_default")
    row = map_applicant(
        "uci_credit_default", generate_applicants(1, seed=3)[0][0], model.profile
    )
    row["age"] = 999
    violations = validate_row("uci_credit_default", row, model.profile)
    assert any("outside training range" in item for item in violations)


@pytest.mark.parametrize(
    ("path", "name", "model_name"),
    [
        ("targets/real/uci-credit-default.yaml", "uci-credit-default", "uci_credit_default"),
        ("targets/real/adult-income.yaml", "adult-income", "adult_income"),
    ],
)
def test_yaml_adapters_build_and_report_capabilities(path, name, model_name):
    adapter = build_target(path, load_config())
    assert adapter.name == name
    assert adapter.real_model == model_name
    assert adapter.base_url == "http://127.0.0.1:8030"
    assert adapter.supported_probes == {"gender"}
    assert set(adapter.unsupported_details) == {
        "pincode_group",
        "name_group",
        "intersectional",
    }
    assert adapter.supports_mitigation is False
    assert adapter.probe_cap == 100000


async def test_real_service_scores_batches(transport):
    adapter = build_target(
        "targets/real/adult-income.yaml", load_config(), transport=transport
    )
    health = await adapter.health()
    assert health["status"] == "ok"
    assert "adult_income" in health["models"]

    people, _ = generate_applicants(6, seed=5)
    responses = await adapter.score_batch(people)
    assert len(responses) == 6
    assert all(isinstance(item.approved, bool) for item in responses)
    assert all(0 <= item.score <= 1000 for item in responses)
    assert adapter.probes_used == 6


@pytest.mark.parametrize("model_name", ["uci_credit_default", "adult_income"])
def test_metrics_record_holdout_and_fairlearn(model_name):
    metrics = load_real_model(model_name).metrics
    assert 0.5 < metrics["holdout"]["accuracy"] <= 1.0
    assert 0.5 < metrics["holdout"]["roc_auc"] <= 1.0
    assert metrics["protected_attribute_in_features"] is True
    assert "sex" in metrics["fairlearn_holdout"]
    assert metrics["fairlearn_holdout"]["sex"]["counts"]
    assert metrics["seed"] == 42
    assert metrics["dataset"]["license"] == "CC BY 4.0"


def _small_config() -> dict:
    config = load_config()
    config["data"]["n_observational"] = 200
    config["audit"]["n_pairs"] = 40
    config["audit"]["min_pairs"] = 5
    config["audit"]["matched_n_pairs"] = 40
    config["audit"]["bootstrap_iterations"] = 50
    return config


@pytest.mark.parametrize(
    "path", ["targets/real/uci-credit-default.yaml", "targets/real/adult-income.yaml"]
)
def test_audit_skips_unsupported_probes_and_reports_it(path, transport):
    config = _small_config()
    adapter = build_target(path, config, transport=transport)
    events, report = collect_audit(
        2,
        adapter.base_url,
        config,
        seed=3,
        include_mitigation=False,
        include_narrative=False,
        target=adapter,
    )
    assert report.observational["supported_probes"] == ["gender"]
    assert set(report.observational["skipped_probes"]) == {
        "pincode_group",
        "name_group",
        "intersectional",
    }
    assert {finding.attribute_or_subgroup for finding in report.findings} <= {
        "gender=female",
        "gender=male",
    }
    assert all(
        "pincode_group" not in finding.attribute_or_subgroup
        and "name_group" not in finding.attribute_or_subgroup
        for finding in report.findings
    )
    assert report.observational["intersectional_cells"] == []
    skipped_events = [
        event for event in events if event.payload.get("skipped") is True
    ]
    assert len(skipped_events) >= 3
    assert any("pincode_group" in event.message for event in skipped_events)
    assert any("intersectional" in event.message for event in skipped_events)
    assert adapter.probes_used > 0


def test_real_and_llm_packages_never_import_sandbox_scoring():
    violations: list[str] = []
    for package in ("real", "llm"):
        root = REPO_ROOT / "targets" / package
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if name in {"sandbox", "sandbox.models", "sandbox.api"}:
                        violations.append(f"{path.name}: {name}")
    assert not violations, violations


def test_metrics_json_is_serialisable_and_has_no_secret():
    for model_name in ("uci_credit_default", "adult_income"):
        text = (
            REPO_ROOT / "data" / "real" / "artifacts" / f"{model_name}.metrics.json"
        ).read_text(encoding="utf-8")
        payload = json.loads(text)
        assert payload["model"] == model_name
        assert "api_key" not in text.lower()
