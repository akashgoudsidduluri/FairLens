"""R1 type-generation test: checked-in TypeScript must match OpenAPI."""

from __future__ import annotations

from config_loader import REPO_ROOT

from api.app import app
from api.generate_types import render_types


def test_generated_types_match_openapi():
    checked_in = REPO_ROOT / "web" / "src" / "api-types.ts"
    assert checked_in.exists(), "web/src/api-types.ts is missing"
    expected = render_types(app.openapi())
    actual = checked_in.read_text(encoding="utf-8")
    assert actual == expected, (
        "web/src/api-types.ts is stale. "
        "Regenerate with: python -m api.generate_types"
    )


def test_generated_types_include_stream_contracts():
    text = (REPO_ROOT / "web" / "src" / "api-types.ts").read_text(encoding="utf-8")
    for name in ("AgentEvent", "ProbeEvent", "StreamEvent", "AuditReport"):
        assert f"interface {name}" in text or f"type {name}" in text
