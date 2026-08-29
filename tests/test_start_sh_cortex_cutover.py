from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SH = REPO_ROOT / "scripts" / "start.sh"
CUTOVER_SH = REPO_ROOT / "scripts" / "cutover-to-planes.sh"
PREFLIGHT_SH = REPO_ROOT / "scripts" / "preflight-tests.sh"
PEP668_INSTALL = (
    "python3 -m venv .venv && "
    ".venv/bin/python -m pip install --upgrade --force-reinstall -e ."
)


def _write_fake_python(
    path: Path,
    *,
    cortex: bool,
    textual: bool,
    cost_config: bool = True,
    cockpit_app: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""#!/usr/bin/env bash
if [[ "${{1:-}}" != "-c" ]]; then
  exit 90
fi
if [[ -n "${{EXPECTED_REPO:-}}" && "${{PYTHONPATH:-}}" != "$EXPECTED_REPO" ]]; then
  exit 91
fi
if [[ "${{2:-}}" == *"import paulsha_cortex.cli"* && "{int(cortex)}" != "1" ]]; then
  exit 1
fi
if [[ "${{2:-}}" == *"import paulshaclaw.cost.config"* && "{int(cost_config)}" != "1" ]]; then
  exit 1
fi
if [[ "${{2:-}}" == *"import paulshaclaw.cockpit.app"* && "{int(cockpit_app)}" != "1" ]]; then
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


def _write_fake_preflight_python(path: Path, log_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""#!/usr/bin/env bash
if [[ "${{1:-}}" == "-c" ]]; then
  if [[ -n "${{EXPECTED_REPO:-}}" && "${{PYTHONPATH:-}}" != "$EXPECTED_REPO" ]]; then
    exit 91
  fi
  exit 0
fi
printf 'PYTHONPATH=%s\\nARGS=%s\\n' "${{PYTHONPATH:-}}" "$*" > "{log_path}"
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_systemctl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "${SYSTEMCTL_LOG:?}"
case "$*" in
  *" daemon-reload"*) exit "${DAEMON_RELOAD_STATUS:-0}" ;;
  *" stop "*|*" disable "*) exit "${LEGACY_COMMAND_STATUS:-0}" ;;
  *" reset-failed "*) exit "${RESET_STATUS:-0}" ;;
  *" enable --now "*) exit "${ENABLE_STATUS:-0}" ;;
  *" restart demo-monitor.service"*) exit "${MONITOR_RESTART_STATUS:-0}" ;;
  *" is-active --quiet demo-monitor.service"*)
    count=$(grep -c 'is-active --quiet demo-monitor.service' "${SYSTEMCTL_LOG}")
    if (( count > 1 )); then exit "${MONITOR_POST_ACTIVE_STATUS:-0}"; fi
    exit "${MONITOR_ACTIVE_STATUS:-0}"
    ;;
  *" restart demo-manager.service"*) exit "${MANAGER_RESTART_STATUS:-0}" ;;
  *" is-active --quiet demo-manager.service"*) exit "${MANAGER_ACTIVE_STATUS:-0}" ;;
  *" is-active paulshaclaw-"*|*" is-active demo-manager."*)
    printf '%s\n' "${LEGACY_ACTIVE_STATE:-inactive}"
    exit 0
    ;;
  *" is-enabled paulshaclaw-"*|*" is-enabled demo-manager."*)
    printf '%s\n' "${LEGACY_ENABLED_STATE:-disabled}"
    exit 0
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_pipx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "${PIPX_LOG:?}"
if [[ "$*" == *"paulsha-hippo"* ]]; then
  exit "${HIPPO_INSTALL_STATUS:-0}"
fi
if [[ "$*" == *"paulsha-cortex"* ]]; then
  exit "${CORTEX_PIPX_STATUS:-0}"
fi
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_cortex(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "${CORTEX_LOG:?}"
exit "${CORTEX_INSTALL_STATUS:-0}"
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_hippo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """#!/usr/bin/env bash
case "$*" in
  "init") exit "${HIPPO_INIT_STATUS:-0}" ;;
  "install hooks") exit "${HIPPO_HOOKS_STATUS:-0}" ;;
  "install service") exit "${HIPPO_SERVICE_STATUS:-0}" ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_resolver(repo: Path, bin_dir: Path, *, psc_python: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    env["EXPECTED_REPO"] = str(repo)
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


def _run_service_resolver(service: Path, repo: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "REPO": str(repo),
            "EXPECTED_REPO": str(repo),
        }
    )
    env.pop("PSC_PYTHON", None)
    env.pop("PY", None)
    return subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            'source "$1" --source-only; printf "%s\\n" "$PY"',
            "bash",
            str(service),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_preflight_script(repo: Path, python: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": "/usr/bin:/bin",
            "PSC_PYTHON": str(python),
            "EXPECTED_REPO": str(repo),
        }
    )
    return subprocess.run(
        [str(repo / "scripts" / "preflight-tests.sh")],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_cutover_function(
    command: str,
    bin_dir: Path,
    tmp_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
            "PIPX_LOG": str(tmp_path / "pipx.log"),
            "CORTEX_LOG": str(tmp_path / "cortex.log"),
            "PSC_CUTOVER_SETTLE_SECONDS": "0",
        }
    )
    env.update(extra_env or {})
    return subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            f'source "$1" --source-only; {command}',
            "bash",
            str(CUTOVER_SH),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


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


def test_operator_python_prefers_repo_venv_over_full_system_python(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    repo_python = repo / ".venv/bin/python"
    _write_fake_python(bin_dir / "python3", cortex=True, textual=True)
    _write_fake_python(repo_python, cortex=True, textual=True)

    completed = _run_resolver(repo, bin_dir)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(repo_python)


@pytest.mark.parametrize("missing", ["cortex", "cost_config", "cockpit_app", "textual"])
def test_operator_python_rejects_missing_runtime_module(tmp_path: Path, missing: str) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    psc_python = tmp_path / "psc" / "python"
    repo_python = repo / ".venv/bin/python"
    availability = {
        "cortex": True,
        "cost_config": True,
        "cockpit_app": True,
        "textual": True,
    }
    availability[missing] = False
    _write_fake_python(psc_python, **availability)
    _write_fake_python(repo_python, cortex=True, textual=True)
    _write_fake_python(bin_dir / "python3", cortex=False, textual=False)

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


def test_service_scripts_share_operator_runtime_resolver() -> None:
    for name in ("dream", "cost", "bot"):
        src = (REPO_ROOT / "scripts" / f"service-{name}.sh").read_text(encoding="utf-8")
        assert 'source "$REPO/scripts/start.sh" --source-only' in src
        assert 'resolve_operator_python "$REPO"' in src
        assert PEP668_INSTALL in src
        assert "pip install --user" not in src


def test_preflight_script_shares_operator_runtime_resolver() -> None:
    src = PREFLIGHT_SH.read_text(encoding="utf-8")
    assert 'source "$script_dir/start.sh" --source-only' in src
    assert 'resolve_operator_python "$repo_root"' in src
    assert 'exec env PYTHONPATH="$repo_root" "$python_bin" -m pytest' in src


def test_standalone_service_scripts_reuse_operator_resolver(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    repo_python = repo / ".venv/bin/python"
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "start.sh").symlink_to(START_SH)
    _write_fake_python(bin_dir / "python3", cortex=False, textual=True)
    _write_fake_python(repo_python, cortex=True, textual=True)

    for name in ("cost", "dream", "bot"):
        completed = _run_service_resolver(REPO_ROOT / "scripts" / f"service-{name}.sh", repo, bin_dir)
        assert completed.returncode == 0, f"service-{name}: {completed.stderr}"
        assert completed.stdout.strip() == str(repo_python)


def test_preflight_script_reuses_operator_resolver_in_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    (repo / "tests").mkdir(parents=True)
    (repo / "custom-skills" / "bro" / "tests").mkdir(parents=True)
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "start.sh").symlink_to(START_SH)
    (scripts_dir / "preflight-tests.sh").symlink_to(PREFLIGHT_SH)

    log_path = tmp_path / "preflight.log"
    python = tmp_path / "psc" / "python"
    _write_fake_preflight_python(python, log_path)

    completed = _run_preflight_script(repo, python)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert log_path.read_text(encoding="utf-8") == (
        f"PYTHONPATH={repo}\n"
        f"ARGS=-m pytest {repo}/tests/ {repo}/custom-skills/bro/tests/ -q\n"
    )


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


def test_cutover_uses_errexit() -> None:
    assert "set -euo pipefail" in CUTOVER_SH.read_text(encoding="utf-8")


def test_cutover_pin_lookup_is_pipefail_safe_with_duplicate_matches(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    pin = "paulsha-hippo@" + "a" * 40
    repo.joinpath("pyproject.toml").write_text(
        (f'"{pin}"\n' * 10_000),
        encoding="utf-8",
    )

    completed = _run_cutover_function(
        f'pin_of "{repo}" paulsha-hippo',
        tmp_path / "bin",
        tmp_path,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == pin


@pytest.mark.parametrize(
    ("extra_env", "expected_status"),
    [
        ({"ENABLE_STATUS": "1"}, 1),
        ({"RESET_STATUS": "1"}, 1),
        ({"MONITOR_RESTART_STATUS": "1"}, 1),
        ({"MONITOR_ACTIVE_STATUS": "1"}, 1),
        ({"MONITOR_POST_ACTIVE_STATUS": "1"}, 1),
        ({"MANAGER_RESTART_STATUS": "1"}, 1),
        ({"MANAGER_ACTIVE_STATUS": "1"}, 1),
        ({}, 0),
    ],
)
def test_cutover_systemd_gate_is_fail_closed(
    tmp_path: Path, extra_env: dict[str, str], expected_status: int
) -> None:
    bin_dir = tmp_path / "bin"
    _write_fake_systemctl(bin_dir / "systemctl")

    completed = _run_cutover_function(
        "enable_and_verify_cortex_services demo",
        bin_dir,
        tmp_path,
        extra_env=extra_env,
    )

    assert completed.returncode == expected_status, completed.stderr


@pytest.mark.parametrize(
    ("extra_env", "expected_status"),
    [
        ({"HIPPO_INSTALL_STATUS": "1"}, 1),
        ({"CORTEX_PIPX_STATUS": "1"}, 1),
        ({}, 0),
    ],
)
def test_cutover_pipx_installs_are_fail_closed(
    tmp_path: Path, extra_env: dict[str, str], expected_status: int
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    repo.joinpath("pyproject.toml").write_text(
        '"paulsha-hippo @ git+https://example.invalid/paulsha-hippo@' + "a" * 40 + '"\n'
        '"paulsha-cortex @ git+https://example.invalid/paulsha-cortex@' + "b" * 40 + '"\n',
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    _write_fake_pipx(bin_dir / "pipx")

    completed = _run_cutover_function(
        f'install_plane_clis "{repo}"',
        bin_dir,
        tmp_path,
        extra_env=extra_env,
    )

    assert completed.returncode == expected_status, completed.stderr


@pytest.mark.parametrize("install_status", [0, 1])
def test_cutover_cortex_install_is_fail_closed(tmp_path: Path, install_status: int) -> None:
    bin_dir = tmp_path / "bin"
    _write_fake_cortex(bin_dir / "cortex")

    completed = _run_cutover_function(
        'install_cortex_service_units demo "/tmp/repo"',
        bin_dir,
        tmp_path,
        extra_env={"CORTEX_INSTALL_STATUS": str(install_status)},
    )

    assert completed.returncode == install_status, completed.stderr


@pytest.mark.parametrize(
    ("extra_env", "expected_status"),
    [
        ({"HIPPO_INIT_STATUS": "1"}, 1),
        ({"HIPPO_HOOKS_STATUS": "1"}, 1),
        ({}, 0),
    ],
)
def test_cutover_hippo_init_and_hooks_are_fail_closed(
    tmp_path: Path, extra_env: dict[str, str], expected_status: int
) -> None:
    bin_dir = tmp_path / "bin"
    _write_fake_hippo(bin_dir / "hippo")
    completed = _run_cutover_function(
        "initialize_hippo",
        bin_dir,
        tmp_path,
        extra_env=extra_env,
    )
    assert completed.returncode == expected_status, completed.stderr


def test_cutover_hippo_cli_is_required(tmp_path: Path) -> None:
    completed = _run_cutover_function("initialize_hippo", tmp_path / "bin", tmp_path)
    assert completed.returncode != 0


@pytest.mark.parametrize("service_status", [0, 1])
def test_cutover_hippo_service_propagates_status(tmp_path: Path, service_status: int) -> None:
    bin_dir = tmp_path / "bin"
    _write_fake_hippo(bin_dir / "hippo")
    completed = _run_cutover_function(
        "install_hippo_service",
        bin_dir,
        tmp_path,
        extra_env={"HIPPO_SERVICE_STATUS": str(service_status)},
    )
    assert completed.returncode == service_status, completed.stderr


@pytest.mark.parametrize(
    ("extra_env", "expected_status"),
    [
        ({"LEGACY_COMMAND_STATUS": "1"}, 0),
        ({"LEGACY_ACTIVE_STATE": "active"}, 1),
        ({"LEGACY_ENABLED_STATE": "enabled"}, 1),
        ({"DAEMON_RELOAD_STATUS": "1"}, 1),
    ],
)
def test_cutover_legacy_retirement_verifies_final_state(
    tmp_path: Path, extra_env: dict[str, str], expected_status: int
) -> None:
    bin_dir = tmp_path / "bin"
    _write_fake_systemctl(bin_dir / "systemctl")
    completed = _run_cutover_function(
        "retire_legacy_services",
        bin_dir,
        tmp_path,
        extra_env=extra_env,
    )
    assert completed.returncode == expected_status, completed.stderr


@pytest.mark.parametrize("failure", ["mkdir", "write"])
def test_cutover_monitor_config_failure_is_nonzero(tmp_path: Path, failure: str) -> None:
    config_root = tmp_path / "config"
    if failure == "mkdir":
        config_root.write_text("not a directory", encoding="utf-8")
    else:
        config_root.mkdir()
        (config_root / "project-cortex.yaml").mkdir()
    completed = _run_cutover_function(
        f'ensure_monitor_project_config "{config_root}" "{tmp_path / "legacy.yaml"}" "/workspace"',
        tmp_path / "bin",
        tmp_path,
    )
    assert completed.returncode != 0


# ---------------------------------------------------------------------------
# #285：start.sh 不得覆寫他人的 <instance>-manager.env
# ---------------------------------------------------------------------------


def _run_ensure_cortex_services(tmp_path: Path, *, existing_repo_root: str | None) -> tuple[subprocess.CompletedProcess[str], Path]:
    """在假 HOME 下呼叫 ensure_cortex_services，回傳結果與 fake PY 的呼叫 log。

    fake PY 會把每次呼叫的參數寫進 log；install service 是否被執行由該 log 判定。
    """
    home = tmp_path / "home"
    (home / ".agents" / "core" / "runtime").mkdir(parents=True, exist_ok=True)
    (home / ".agents" / "log").mkdir(parents=True, exist_ok=True)
    call_log = tmp_path / "py-calls.log"

    fake_py = tmp_path / "fake-python"
    fake_py.write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{call_log}"\n',
        encoding="utf-8",
    )
    fake_py.chmod(fake_py.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if existing_repo_root is not None:
        (home / ".agents" / "core" / "runtime" / "psc-test-manager.env").write_text(
            f"PSC_INSTANCE=psc-test\nPSC_REPO_ROOT={existing_repo_root}\n",
            encoding="utf-8",
        )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PSC_INSTANCE": "psc-test",
            "PSC_AGENTS_ROOT": str(home / ".agents"),
            "PSC_MANAGER_SPECS_DIR": str(tmp_path / "specs"),
        }
    )
    completed = subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            f'source "$1" --source-only; PY="{fake_py}"; REPO="{REPO_ROOT}"; ensure_cortex_services',
            "bash",
            str(START_SH),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, call_log


def test_ensure_cortex_services_skips_install_when_manager_env_belongs_to_other_repo(tmp_path: Path) -> None:
    """#285 問題 B：既有 manager.env 指向別的 repo 時不得覆寫。

    cortex 的 `install service` 會就地覆寫 managed keys（含 PSC_REPO_ROOT / PY），
    在同時裝了 paulshaclaw 與 paulsha-cortex 的機器上會劫持對方的 instance，
    症狀是 cortex 所有 work-action 掛住、且潛伏到下次重啟才爆。
    """
    # 取 tmp_path 底下的假路徑而非字面 `/home/<user>/...`：本 repo 為 public，
    # R-21 會把個人絕對路徑樣式判為 structural finding（即使使用者名是虛構的）。
    # 這裡只需要「一個不等於本 repo root 的路徑」，用 tmp_path 同樣達意且更 hermetic。
    completed, call_log = _run_ensure_cortex_services(
        tmp_path, existing_repo_root=str(tmp_path / "other-owner" / "paulsha-cortex")
    )

    calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    assert "install service" not in calls, f"不該呼叫 install service，實際呼叫：{calls}"
    assert "PSC_REPO_ROOT" in completed.stderr, completed.stderr
    assert "不覆寫" in completed.stderr, completed.stderr


def test_ensure_cortex_services_installs_when_manager_env_is_ours(tmp_path: Path) -> None:
    """對照組：manager.env 指向本 repo（或不存在）時維持既有行為。"""
    completed, call_log = _run_ensure_cortex_services(
        tmp_path, existing_repo_root=str(REPO_ROOT)
    )

    calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    assert "install service" in calls, f"應照舊呼叫 install service，實際呼叫：{calls}"


def test_ensure_cortex_services_installs_when_no_manager_env(tmp_path: Path) -> None:
    completed, call_log = _run_ensure_cortex_services(tmp_path, existing_repo_root=None)

    calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    assert "install service" in calls, f"應照舊呼叫 install service，實際呼叫：{calls}"


def test_ensure_cortex_services_installs_when_manager_env_path_is_symlinked_equivalent(
    tmp_path: Path,
) -> None:
    """#285 follow-up：等價路徑不得被誤判成別人的 repo。

    symlink checkout、trailing slash、`/a/../a` 都指向同一個 repo；直接字串
    比對會誤判成「別的 repo」而錯誤跳過 install service。
    """
    link = tmp_path / "repo-symlink"
    link.symlink_to(REPO_ROOT)

    for variant in (f"{REPO_ROOT}/", str(link), f"{REPO_ROOT}/./"):
        completed, call_log = _run_ensure_cortex_services(
            tmp_path / f"case-{abs(hash(variant))}", existing_repo_root=variant
        )
        calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
        assert "install service" in calls, (
            f"{variant} 與本 repo 等價，不該被判成別的 repo；stderr={completed.stderr}"
        )
