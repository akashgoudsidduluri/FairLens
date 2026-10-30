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

SUITE_B_CSV = """suite,model_id,seed,materiality,runtime_s,cells_examined,cells_tested,discovery_pairs,confirmation_pairs,candidates,confirmed,kept,rejected,immaterial,merged,kept_ids,expectation,misses,notes,false_alarm_before,false_alarm_after,mde_n200,mde_n1000,planned_applicants,diagnostic_applicants,probe_cap,dose_response,error
B,8,1,0.02,60.0,110,110,26000,6400,16,16,1,11,0,15,gen-age-45plus,PASS,,"context-specific, not the main effect",27,1,0.099,0.044,68800,4000,100000,45:+0.0000; 55:+0.6100,
B,8,2,0.02,62.0,110,110,26000,6400,16,16,1,11,0,15,gen-age-45plus,PASS,,,27,1,0.099,0.044,68800,4000,100000,45:+0.0000; 55:+0.6100,
B,8,1,0.01,58.0,110,110,26000,6400,16,16,2,10,0,14,gen-age-45plus,PASS,,,26,2,0.099,0.044,68800,4000,100000,,
B,15,1,0.02,55.0,110,110,26000,0,0,0,0,0,0,0,,PASS,,,0,0,0.099,0.044,68800,0,100000,,
"""

SUITE_B_FAIRLEARN_CSV = """model_id,attribute,n,dp_difference,eo_difference,approval_rates
8,gender,4000,0.12,0.05,female=0.4; male=0.5
8,age_band,4000,0.31,0.09,<35=0.2; 45+=0.6
15,gender,4000,0.04,0.02,female=0.45; male=0.49
"""

SUITE_B_MARKDOWN = "# Suite B and the generalized protocol (R5 Step 7)\n\nLimitations stay attached.\n"

SUITE_B_R51_CSV = """suite,model_id,seed,materiality,runtime_s,cells_examined,cells_tested,discovery_pairs,confirmation_pairs,candidates,confirmed,kept,rejected,immaterial,merged,kept_ids,expectation,misses,notes,false_alarm_before,false_alarm_after,mde_n200,mde_n1000,planned_applicants,diagnostic_applicants,probe_cap,dose_response,error
B,8,1,0.02,70.0,110,110,26000,6400,16,16,1,11,0,15,gen-age-45plus-credit_score-high,PASS,,,5,1,0.099,0.044,68800,4000,100000,45:+0.0000; 55:+0.6100,
B,8,2,0.02,72.0,110,110,26000,6400,16,16,1,11,0,15,gen-age-45plus-credit_score-high,PASS,,,5,1,0.099,0.044,68800,4000,100000,45:+0.0000; 55:+0.6100,
B,15,1,0.02,65.0,110,110,26000,0,0,0,0,0,0,0,,PASS,,,0,0,0.099,0.044,68800,0,100000,,
"""

SUITE_B_R51_FAIRLEARN_CSV = SUITE_B_FAIRLEARN_CSV

SUITE_B_R51_MARKDOWN = (
    "# R5.1 sibling-context merge - protocol 2\n\n"
    "Protocol 1 is shown beside it, not replaced.\n"
)


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
    (directory / "suite_b.csv").write_text(SUITE_B_CSV, encoding="utf-8")
    (directory / "suite_b_fairlearn.csv").write_text(
        SUITE_B_FAIRLEARN_CSV, encoding="utf-8"
    )
    (directory / "suite_b.md").write_text(SUITE_B_MARKDOWN, encoding="utf-8")
    (directory / "suite_b_r51.csv").write_text(SUITE_B_R51_CSV, encoding="utf-8")
    (directory / "suite_b_r51_fairlearn.csv").write_text(
        SUITE_B_R51_FAIRLEARN_CSV, encoding="utf-8"
    )
    (directory / "suite_b_r51.md").write_text(
        SUITE_B_R51_MARKDOWN, encoding="utf-8"
    )


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
    assert evidence["suite_b"]["models"] == []
    assert evidence["suite_b"]["markdown"] == ""
    assert evidence["suite_b_r51"]["models"] == []
    assert evidence["suite_b_r51"]["markdown"] == ""
    assert all(not source["present"] for source in evidence["sandbox"]["sources"])
    assert all(not source["present"] for source in evidence["real"]["sources"])
    assert all(not source["present"] for source in evidence["suite_b"]["sources"])
    assert all(
        not source["present"] for source in evidence["suite_b_r51"]["sources"]
    )


def test_suite_b_aggregation_ignores_the_sensitivity_rows(tmp_path):
    _write_results(tmp_path)
    suite_b = build_evidence(tmp_path)["suite_b"]

    # Three suite B rows at the pre-registered 2%; the 1% row stays in the CSV
    # but is not averaged into the headline table.
    assert suite_b["runs"] == 3
    assert suite_b["expectation_passed"] == 3
    assert suite_b["expectation_total"] == 3
    assert [model["model_id"] for model in suite_b["models"]] == [8, 15]

    eight, control = suite_b["models"]
    assert eight["kept_mean"] == 1
    assert eight["kept_ids"] == ["gen-age-45plus"]
    assert eight["candidates_mean"] == 16
    assert eight["confirmed_mean"] == 16
    assert eight["cells_examined"] == 110
    assert eight["false_alarm_before"] == 54
    assert eight["false_alarm_after"] == 2
    assert eight["mde_n200"] == pytest.approx(0.099)
    assert eight["mde_n1000"] == pytest.approx(0.044)
    assert eight["notes"] == ["context-specific, not the main effect"]
    assert eight["dose_response"] == ["45:+0.0000; 55:+0.6100"]
    # The Fairlearn gap is the largest DP difference for that model and names
    # the attribute it came from.
    assert eight["max_dp_gap"] == pytest.approx(0.31)
    assert eight["max_dp_attribute"] == "age_band"

    assert control["kept_mean"] == 0
    assert control["confirmed_mean"] == 0
    assert control["max_dp_gap"] == pytest.approx(0.04)
    assert suite_b["markdown"].startswith("# Suite B")


def test_suite_b_r51_is_aggregated_from_its_own_files(tmp_path):
    _write_results(tmp_path)
    evidence = build_evidence(tmp_path)
    protocol_1 = evidence["suite_b"]
    protocol_2 = evidence["suite_b_r51"]

    # The two protocols are read independently: protocol 1's false-alarm count
    # is unchanged by the protocol-2 fixture.
    assert protocol_1["models"][0]["false_alarm_before"] == 54
    assert protocol_2["runs"] == 3
    assert protocol_2["expectation_passed"] == 3
    assert protocol_2["expectation_total"] == 3
    assert [model["model_id"] for model in protocol_2["models"]] == [8, 15]

    eight, control = protocol_2["models"]
    assert eight["kept_mean"] == 1
    assert eight["kept_ids"] == ["gen-age-45plus-credit_score-high"]
    assert eight["false_alarm_before"] == 10
    assert eight["false_alarm_after"] == 2
    assert control["kept_mean"] == 0
    assert protocol_2["markdown"].startswith("# R5.1")
    assert [source["present"] for source in protocol_2["sources"]] == [
        True,
        True,
        True,
    ]


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
    assert body["suite_b"]["models"][0]["model_id"] == 8
    assert body["suite_b"]["models"][0]["kept_ids"] == ["gen-age-45plus"]
    assert body["suite_b"]["markdown"].startswith("# Suite B")
    assert body["suite_b_r51"]["models"][0]["model_id"] == 8
    assert body["suite_b_r51"]["models"][0]["kept_ids"] == [
        "gen-age-45plus-credit_score-high"
    ]
    assert body["suite_b_r51"]["markdown"].startswith("# R5.1")
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
        assert body["suite_b"]["models"] == []
        assert body["suite_b"]["sources"][0]["present"] is False
        assert body["suite_b_r51"]["models"] == []
        assert body["suite_b_r51"]["sources"][0]["present"] is False
    await context.__aexit__(None, None, None)
