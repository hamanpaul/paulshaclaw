from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SH = REPO_ROOT / "scripts" / "start.sh"


def test_start_sh_has_no_dead_manager_or_monitor_refs() -> None:
    src = START_SH.read_text(encoding="utf-8")
    prefix = "paulshaclaw"

    for dead_ref in (
        "service-" + "manager.sh",
        "start_manager_loop",
        f"{prefix}.monitor",
        f"{prefix}.coordinator.manager_daemon",
        "scripts/" + "coordinator",
    ):
        assert dead_ref not in src, f"start.sh 仍引用已刪的 {dead_ref}"

    assert "cortex install service" in src


def test_start_sh_is_bash_parseable() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(START_SH)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_operator_python_prefers_planes_having_interpreter() -> None:
    """start.sh 不再硬預設 repo .venv；改為挑能 import paulsha_cortex 的 python
    （PSC_PYTHON 可覆寫），找不到時 fail-fast 給指引而非裸 ModuleNotFoundError。"""
    src = START_SH.read_text(encoding="utf-8")
    assert "import paulsha_cortex" in src, "start.sh 應以 import 探測選用有 planes 的 python"
    assert "PSC_PYTHON" in src, "start.sh 應支援 PSC_PYTHON 覆寫"
    assert "pip install --user -e ." in src, "缺 planes 時應給明確安裝指引"


def test_service_scripts_prefer_planes_python_over_venv() -> None:
    for name in ("dream", "cost", "bot"):
        src = (REPO_ROOT / "scripts" / f"service-{name}.sh").read_text(encoding="utf-8")
        assert "PSC_PYTHON" in src, f"service-{name}.sh 應優先 PSC_PYTHON / python3 而非 .venv"
