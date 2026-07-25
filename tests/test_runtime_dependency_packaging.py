from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_operator_shell_declares_direct_runtime_dependencies() -> None:
    dependencies = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]

    assert "PyYAML>=6.0" in dependencies
    assert "textual==0.61.1" in dependencies
    assert not any(dependency.lower().startswith("watchdog") for dependency in dependencies)


def test_ci_smokes_editable_install_runtime_closure_without_stage_requirements() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")

    assert "requirements-stage9.txt" not in workflow
    assert "requirements-stage11.txt" not in workflow
    assert workflow.index("Smoke import editable install runtime closure") < workflow.index("Install test runner")
    for module_name in (
        "paulshaclaw",
        "paulsha_cortex",
        "paulsha_hippo",
        "paulshaclaw.cost.config",
        "paulshaclaw.cockpit",
        "textual",
    ):
        assert f"import {module_name}" in workflow
