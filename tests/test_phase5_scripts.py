"""Phase 5 integration checks: launchers and graceful API failure in the UI."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from auditor.prober import ProberError
from config_loader import load_config
from schemas import AgentEvent

ROOT = Path(__file__).resolve().parents[1]


def test_launchers_use_the_sandbox_entrypoint_and_demo_ports():
    for name in ("run.sh", "run.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "sandbox.serve" in text, name
        assert "8010" in text, name
        assert "8501" in text, name
        assert "Model 2" in text and "Model 7" in text and "Model 5" in text, name


def test_ui_shows_friendly_error_when_api_is_unreachable(monkeypatch, tmp_path):
    config = load_config()
    config["certificate"]["db_path"] = str(tmp_path / "unreachable.db")
    monkeypatch.setattr("config_loader.load_config", lambda *args, **kwargs: config)

    def unreachable(*args, **kwargs):
        yield AgentEvent(agent="planner", message="Audit plan prepared.")
        yield AgentEvent(agent="planner", message="Audit aborted: sandbox unreachable")
        raise ProberError("Sandbox is unreachable at http://127.0.0.1:1")

    monkeypatch.setattr("auditor.pipeline.run_audit", unreachable)
    at = AppTest.from_file(str(ROOT / "ui" / "app.py"), default_timeout=60)
    at.run()
    next(button for button in at.button if button.label == "Run audit").click()
    at.run()

    assert not at.exception, [exc.value for exc in at.exception]
    assert any("Audit could not run" in error.value for error in at.error)
    assert any("Check the API URL" in info.value for info in at.info)
    assert any("Audit aborted" in markdown.value for markdown in at.markdown)
