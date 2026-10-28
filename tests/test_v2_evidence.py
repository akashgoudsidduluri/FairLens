"""Evidence API tests: aggregates come from the CSV files, not literals."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from api.app import create_app
from api.evidence import build_evidence
from config_loader import load_config


SANDBOX_CSV = """model_id,seed,materiality,runtime_s,runtime_under_60,kept,rejected,immaterial,kept_ids,expectation,misses,false_alarm_before,false_alarm_after,narrative_source,number_check_passed,number_check_tokens,error
1,1,0.02,10.0,True,0,3,0,,PASS,,2,0,template,True,8,
1,2,0.02,20.0,True,0,3,0,,PASS,,2,0,template,True,8,
2,1,0.02,30.0,True,1,0,0,,MISS,"a miss, stated",,,template,False,0,
2,2,0.02,40.0,True,1,0,0,,MISS,"a miss, stated",,,template,False,0,
"""

REAL_CSV = """model,seed,runtime_s,probes_used,supported_probes,skipped_probes,kept,rejected,immaterial,impact_per_10k,holdout_accuracy,holdout_auc,fairlearn_sex_demographic_parity_difference,fairlearn_sex_equalized_odds_difference,fairlearn_age_demographic_parity_difference,fairlearn_age_equalized_odds_difference,fairlearn_race_demographic_parity_difference,fairlearn_race_equalized_odds_difference,kept_details,rejected_details,immaterial_details,error
adult_income,1,12.0,8000,gender,intersectional,0,0,1,50.0,0.8,0.9,0.2,0.1,0.3,0.2,0.1,0.4,,"","gender=female: net=+0.006", 
adult_income,2,13.0,8000,gender,intersectional,0,0,1,100.0,0.8,0.9,0.2,0.1,0.3,0.2,0.1,0.4,,"","gender=female: net=+0.006",
"""

MARKDOWN = """# Real-data target results

**Status: evaluated after pre-registration.**

## Limitations

The probe population is synthetic.
"""


def _config(tmp_path: Path) -> dict:
    config = load_config()
    config["service"]["audit_db"] = str(tmp_path / "audits.db")
    config["certificate"]["db_path"] = str(tmp_path / "certificates.db")
    return config


def _write_results(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.csv").write_text(SANDBOX_CSV, encoding="utf-8")
    (directory / "real_models.csv").write_text(REAL_CSV, encoding="utf-8")
    (directory / "fairlearn.csv").write_text("model_id,attribute\n", encoding="utf-8")
    (directory / "real_models.md").write_text(MARKDOWN, encoding="utf-8")
    (directory / "summary.md").write_text("# Summary\n", encoding="utf-8")


def test_sandbox_aggregation_expected_found_and_false_alarms(tmp_path):
    _write_results(tmp_path)
    evidence = build_evidence(tmp_path)
    sandbox = evidence["sandbox"]

    assert sandbox["runs"] == 4
    assert sandbox["expectation_passed"] == 2
    assert sandbox["expectation_total"] == 4
    assert sandbox["false_alarm_before"] == 4
    assert sandbox["false_alarm_after"] == 0

    first, second = sandbox["models"]
    assert first["model_id"] == 1
    assert first["kept_mean"] == 0
    assert first["rejected_mean"] == 3
    assert first["false_alarm_before"] == 4
    assert first["false_alarm_after"] == 0

    assert second["model_id"] == 2
    assert second["expectation_passed"] == 0
    assert second["expectation_total"] == 2
    assert second["kept_min"] == 1
    assert second["misses"] == ["a miss, stated"]
    assert second["false_alarm_before"] is None


def test_real_aggregation_pairs_fairlearn_with_fairlens(tmp_path):
    _write_results(tmp_path)
    evidence = build_evidence(tmp_path)
    model = evidence["real"]["models"][0]

    assert model["model"] == "adult_income"
    assert model["label"] == "UCI Adult Income"
    assert model["runs"] == 2
    assert model["supported_probes"] == ["gender"]
    assert model["skipped_probes"] == ["intersectional"]
    assert model["kept_mean"] == 0
    assert model["immaterial_mean"] == 1
    assert model["impact_per_10k_mean"] == 75
    assert model["impact_per_10k_min"] == 50
    assert model["impact_per_10k_max"] == 100
    assert model["holdout_accuracy"] == 0.8
    assert model["fairlearn"][0] == {
        "attribute": "sex",
        "demographic_parity_difference": 0.2,
        "equalized_odds_difference": 0.1,
    }
    assert evidence["real"]["markdown"] == MARKDOWN


def test_missing_results_do_not_invent_numbers(tmp_path):
    evidence = build_evidence(tmp_path / "absent")
    assert evidence["sandbox"]["models"] == []
    assert evidence["sandbox"]["runs"] == 0
    assert evidence["sandbox"]["false_alarm_before"] is None
    assert evidence["real"]["models"] == []
    assert evidence["real"]["markdown"] == ""
    assert all(not source["present"] for source in evidence["sandbox"]["sources"])
    assert all(not source["present"] for source in evidence["real"]["sources"])


@pytest.fixture
async def evidence_client(tmp_path):
    results = tmp_path / "results"
    _write_results(results)
    app = create_app(config=_config(tmp_path), evidence_dir=results)
    context = app.router.lifespan_context(app)
    await context.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    try:
        yield client
    finally:
        await client.aclose()
        await context.__aexit__(None, None, None)


async def test_evidence_route_serves_the_computed_payload(evidence_client):
    response = await evidence_client.get("/evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["sandbox"]["runs"] == 4
    assert body["sandbox"]["models"][1]["misses"] == ["a miss, stated"]
    assert body["real"]["models"][0]["fairlearn"][0]["attribute"] == "sex"
    assert body["real"]["markdown"].startswith("# Real-data target results")
    assert body["generated_at"]


async def test_evidence_route_reports_absent_files(tmp_path):
    app = create_app(
        config=_config(tmp_path), evidence_dir=tmp_path / "nothing-here"
    )
    context = app.router.lifespan_context(app)
    await context.__aenter__()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/evidence")
        assert response.status_code == 200
        body = response.json()
        assert body["sandbox"]["models"] == []
        assert body["real"]["sources"][0]["present"] is False
    await context.__aexit__(None, None, None)
