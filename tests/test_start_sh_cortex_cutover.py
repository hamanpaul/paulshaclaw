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
