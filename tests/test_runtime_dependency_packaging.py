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
    # pytest 安裝與 R-19 policy 同步工法合併進「Run test suite」step
    # （見 policy 1.0.17 同步變更）；不再有獨立的「Install test runner」
    # step，改以 pytest 安裝命令本身作為順序錨點，維持原意：smoke import
    # 必須在任何測試專用套件安裝之前，確保它只驗證 operator shell 自身
    # 宣告的 runtime 依賴閉包，不被 pytest 污染 sys.path。
    assert workflow.index("Smoke import editable install runtime closure") < workflow.index(
        "python -m pip install pytest"
    )
    for module_name in (
        "paulshaclaw",
        "paulsha_cortex",
        "paulsha_hippo",
        "paulshaclaw.cost.config",
        "paulshaclaw.cockpit",
        "textual",
    ):
        assert f"import {module_name}" in workflow
