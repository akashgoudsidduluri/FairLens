"""Enforce the black-box claim by static inspection.

The auditor may import schemas.py and sandbox.generator (data generation and
lookup tables). It must never import the sandbox scoring logic or API module.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKED_DIRS = ["auditor", "impact", "trust", "report", "ui"]
FORBIDDEN = {"sandbox.models", "sandbox.api", "sandbox"}
ALLOWED = {"sandbox.generator"}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for dirname in CHECKED_DIRS:
        base = ROOT / dirname
        if base.exists():
            files.extend(base.rglob("*.py"))
    return files


def test_no_forbidden_sandbox_imports():
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name in FORBIDDEN or (name.startswith("sandbox.") and name not in ALLOWED):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {name}")
    assert not violations, "\n".join(violations)


def test_no_dynamic_sandbox_scoring_references():
    pattern = re.compile(r"sandbox\s*\.\s*(models|api)\b")
    violations = []
    for path in _python_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not violations, "\n".join(violations)
