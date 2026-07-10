from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SH = REPO_ROOT / "scripts" / "start.sh"
CUTOVER_SH = REPO_ROOT / "scripts" / "cutover-to-planes.sh"
PEP668_INSTALL = (
    "python3 -m venv .venv && "
    ".venv/bin/python -m pip install --upgrade --force-reinstall -e ."
)


def _write_fake_python(path: Path, *, cortex: bool, textual: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""#!/usr/bin/env bash
if [[ "${{1:-}}" != "-c" ]]; then
  exit 90
fi
if [[ "${{2:-}}" == *"import paulsha_cortex"* && "{int(cortex)}" != "1" ]]; then
  exit 1
fi
if [[ "${{2:-}}" == *"import textual"* && "{int(textual)}" != "1" ]]; then
  exit 1
fi
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_cortex_console_script(path: Path, python: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{python}\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_command_logger(path: Path, log_variable: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" > "${{{log_variable}:?}}"
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_resolver(repo: Path, bin_dir: Path, *, psc_python: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    if psc_python is None:
        env.pop("PSC_PYTHON", None)
    else:
        env["PSC_PYTHON"] = str(psc_python)
    return subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            'source "$1" --source-only; resolve_operator_python "$2"',
            "bash",
            str(START_SH),
            str(repo),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_cutover_install(
    repo: Path, bin_dir: Path, tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bootstrap_log = tmp_path / "bootstrap.log"
    venv_log = tmp_path / "venv.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "BOOTSTRAP_LOG": str(bootstrap_log),
            "VENV_LOG": str(venv_log),
        }
    )
    completed = subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            'source "$1" --source-only; install_operator_runtime "$2"',
            "bash",
            str(CUTOVER_SH),
            str(repo),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, bootstrap_log, venv_log


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


def test_operator_python_error_uses_pep668_safe_repo_venv_install() -> None:
    src = START_SH.read_text(encoding="utf-8")
    assert PEP668_INSTALL in src
    assert "pip install --user" not in src


def test_operator_python_prefers_psc_python_with_full_runtime(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    psc_python = tmp_path / "psc" / "python"
    _write_fake_python(psc_python, cortex=True, textual=True)
    _write_fake_python(bin_dir / "python3", cortex=True, textual=True)
    _write_fake_python(repo / ".venv/bin/python", cortex=True, textual=True)

    completed = _run_resolver(repo, bin_dir, psc_python=psc_python)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(psc_python)


def test_operator_python_rejects_partial_psc_and_uses_repo_venv(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    psc_python = tmp_path / "psc" / "python"
    repo_python = repo / ".venv/bin/python"
    _write_fake_python(psc_python, cortex=True, textual=False)
    _write_fake_python(bin_dir / "python3", cortex=False, textual=True)
    _write_fake_python(repo_python, cortex=True, textual=True)

    completed = _run_resolver(repo, bin_dir, psc_python=psc_python)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(repo_python)


def test_operator_python_uses_cortex_shebang_only_with_full_runtime(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    pipx_python = tmp_path / "pipx" / "python"
    _write_fake_python(bin_dir / "python3", cortex=False, textual=True)
    _write_fake_python(repo / ".venv/bin/python", cortex=False, textual=False)
    _write_fake_python(pipx_python, cortex=True, textual=True)
    _write_cortex_console_script(bin_dir / "cortex", pipx_python)

    completed = _run_resolver(repo, bin_dir)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(pipx_python)


def test_operator_python_rejects_cortex_only_pipx_runtime(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    pipx_python = tmp_path / "pipx" / "python"
    _write_fake_python(bin_dir / "python3", cortex=False, textual=True)
    _write_fake_python(repo / ".venv/bin/python", cortex=False, textual=False)
    _write_fake_python(pipx_python, cortex=True, textual=False)
    _write_cortex_console_script(bin_dir / "cortex", pipx_python)

    completed = _run_resolver(repo, bin_dir)

    assert completed.returncode == 1, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_service_scripts_prefer_planes_python_over_venv() -> None:
    for name in ("dream", "cost", "bot"):
        src = (REPO_ROOT / "scripts" / f"service-{name}.sh").read_text(encoding="utf-8")
        assert "PSC_PYTHON" in src, f"service-{name}.sh 應優先 PSC_PYTHON / python3 而非 .venv"
        assert PEP668_INSTALL in src
        assert "pip install --user" not in src


def test_readme_install_uses_repo_venv_for_operator_runtime() -> None:
    src = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "python3 -m venv .venv" in src
    assert ".venv/bin/python -m pip install --upgrade --force-reinstall -e ." in src
    assert ".venv/bin/python -m pip install pytest" in src
    assert ".venv/bin/python -m pytest tests/ -q" in src
    assert "\npip install --user -e ." not in src


def test_cutover_force_refreshes_repo_venv_from_pyproject(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    bootstrap_python = bin_dir / "python3"
    venv_python = repo / ".venv/bin/python"
    _write_command_logger(bootstrap_python, "BOOTSTRAP_LOG")
    _write_command_logger(venv_python, "VENV_LOG")

    completed, bootstrap_log, venv_log = _run_cutover_install(repo, bin_dir, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert bootstrap_log.read_text(encoding="utf-8").strip() == f"-m venv {repo}/.venv"
    assert venv_log.read_text(encoding="utf-8").strip() == (
        f"-m pip install --upgrade --force-reinstall -e {repo}"
    )


def test_cutover_restarts_monitor_and_keeps_active_check() -> None:
    src = CUTOVER_SH.read_text(encoding="utf-8")
    assert 'systemctl --user restart "${INSTANCE}-monitor.service"' in src
    assert 'systemctl --user is-active "${INSTANCE}-monitor.service"' in src
