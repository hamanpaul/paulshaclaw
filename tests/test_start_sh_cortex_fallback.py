"""start.sh 的 cortex fallback 啟動守則。

回歸情境（2026-07-28）：systemd user session 其實活著並常駐 cortex-manager，
但啟動 start.sh 的 shell 沒有 XDG_RUNTIME_DIR，`systemctl --user` 連不上 bus、
被誤判成 systemd 不可用而走 local fallback；fallback 起的 manager daemon 搶不到
`~/.agents/control/manager.lock` 便靜默退出，start.sh 的 gate 判定啟動失敗
`exit 1`，cockpit 因此起不來。
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SH = REPO_ROOT / "scripts" / "start.sh"


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_py(path: Path) -> None:
    """假 operator python：記錄每次呼叫，daemon/monitor 子命令改成長駐 sleep。"""

    _write_executable(
        path,
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${PY_LOG:?}"
case "$*" in
  *"coordinator.manager_daemon"*)
    if [[ "${MANAGER_EXITS:-0}" == "1" ]]; then exit 1; fi
    exec sleep "${FAKE_SLEEP:-5}"
    ;;
  *"paulsha_cortex.cli monitor"*)
    exec sleep "${FAKE_SLEEP:-5}"
    ;;
esac
exit "${INSTALL_STATUS:-0}"
""",
    )


def _write_fake_systemctl(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${SYSTEMCTL_LOG:?}"
case "$*" in
  *"show-environment"*) exit "${SHOW_ENV_STATUS:-0}" ;;
  *"enable --now"*) exit "${ENABLE_STATUS:-0}" ;;
esac
exit 0
""",
    )


def _run_start_fn(
    command: str,
    tmp_path: Path,
    *,
    requires: str,
    bin_dir: Path | None = None,
    extra_env: dict[str, str] | None = None,
    drop_xdg: bool = True,
) -> subprocess.CompletedProcess[str]:
    """在 source-only 模式下呼叫 start.sh 的單一函式。

    ``requires`` 是被測函式名：先斷言它有被 source 進來，否則 `command not found`
    的非零退出會被 `|| echo FREE` 之類的分支吃掉，變成假通過。
    """

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin" if bin_dir else "/usr/bin:/bin"
    if drop_xdg:
        env.pop("XDG_RUNTIME_DIR", None)
    env.update(extra_env or {})
    guard = f'declare -F {requires} >/dev/null || {{ echo "missing function: {requires}" >&2; exit 97; }}'
    return subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            f'source "$1" --source-only; {guard}; {command}',
            "bash",
            str(START_SH),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _await_log_entry(log: Path, needle: str, timeout: float = 10.0) -> str:
    """等背景進程把自己的呼叫寫進 log。

    fallback 用 `&` 起子進程，start.sh 回到前景時子進程往往還沒寫檔，直接讀會
    看到空 log。等到期望的那筆出現，之後的「不該出現」斷言才有時序錨點。
    """

    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        if needle in text:
            return text
        time.sleep(0.05)
    raise AssertionError(f"等不到 {needle!r} 出現在 {log}，目前內容：{text!r}")


class _LockHolder:
    """在背景進程中持有 manager.lock 的 flock，模擬已常駐的 manager daemon。"""

    def __init__(self, lock_path: Path) -> None:
        self._proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import fcntl, os, sys, time\n"
                "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)\n"
                "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                "sys.stdout.write('locked\\n')\n"
                "sys.stdout.flush()\n"
                "time.sleep(60)\n",
                str(lock_path),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert self._proc.stdout is not None
        assert self._proc.stdout.readline().strip() == "locked"

    def close(self) -> None:
        self._proc.terminate()
        self._proc.wait(timeout=10)


@pytest.fixture()
def held_manager_lock(tmp_path: Path):
    control_root = tmp_path / "control"
    control_root.mkdir(parents=True, exist_ok=True)
    holder = _LockHolder(control_root / "manager.lock")
    try:
        yield control_root
    finally:
        holder.close()


# --- 缺陷 A：XDG_RUNTIME_DIR 缺漏導致 systemd 誤判 ---------------------------


def test_ensure_xdg_runtime_dir_fills_missing_value(tmp_path: Path) -> None:
    runtime = tmp_path / "run-user"
    runtime.mkdir()

    completed = _run_start_fn(
        f'ensure_xdg_runtime_dir "{runtime}"; printf "%s\\n" "${{XDG_RUNTIME_DIR:-UNSET}}"',
        tmp_path,
        requires="ensure_xdg_runtime_dir",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(runtime)


def test_ensure_xdg_runtime_dir_keeps_existing_value(tmp_path: Path) -> None:
    runtime = tmp_path / "run-user"
    runtime.mkdir()
    preset = tmp_path / "preset"
    preset.mkdir()

    completed = _run_start_fn(
        f'ensure_xdg_runtime_dir "{runtime}"; printf "%s\\n" "${{XDG_RUNTIME_DIR:-UNSET}}"',
        tmp_path,
        requires="ensure_xdg_runtime_dir",
        extra_env={"XDG_RUNTIME_DIR": str(preset)},
        drop_xdg=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(preset)


def test_ensure_xdg_runtime_dir_ignores_absent_candidate(tmp_path: Path) -> None:
    completed = _run_start_fn(
        f'ensure_xdg_runtime_dir "{tmp_path / "missing"}"; printf "%s\\n" "${{XDG_RUNTIME_DIR:-UNSET}}"',
        tmp_path,
        requires="ensure_xdg_runtime_dir",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "UNSET"


@pytest.mark.skipif(os.geteuid() == 0, reason="root 無視目錄權限，測不到不可寫分支")
def test_ensure_xdg_runtime_dir_ignores_unwritable_candidate(tmp_path: Path) -> None:
    runtime = tmp_path / "run-user"
    runtime.mkdir(mode=0o500)

    completed = _run_start_fn(
        f'ensure_xdg_runtime_dir "{runtime}"; printf "%s\\n" "${{XDG_RUNTIME_DIR:-UNSET}}"',
        tmp_path,
        requires="ensure_xdg_runtime_dir",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "UNSET"


def test_start_sh_normalizes_xdg_runtime_dir_before_start_lock() -> None:
    """start_lock 也吃 XDG_RUNTIME_DIR，正規化必須早於它，否則同一台機器會有兩個 lock 路徑。"""

    src = START_SH.read_text(encoding="utf-8")
    call_index = src.index("\nensure_xdg_runtime_dir\n")
    lock_index = src.index('start_lock="${PSC_START_LOCK:-${XDG_RUNTIME_DIR:-/tmp}')

    assert call_index < lock_index, "ensure_xdg_runtime_dir 必須在 start_lock 之前呼叫"


# --- 缺陷 B：fallback 撞上已常駐的 manager ----------------------------------


def test_manager_lock_reports_held_when_daemon_alive(tmp_path: Path, held_manager_lock: Path) -> None:
    completed = _run_start_fn(
        "cortex_manager_lock_is_held && echo HELD || echo FREE",
        tmp_path,
        requires="cortex_manager_lock_is_held",
        extra_env={"PSC_CONTROL_ROOT": str(held_manager_lock)},
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "HELD"


def test_manager_lock_reports_free_when_file_is_stale(tmp_path: Path) -> None:
    control_root = tmp_path / "control"
    control_root.mkdir()
    (control_root / "manager.lock").write_text('{"pid": 999999}', encoding="utf-8")

    completed = _run_start_fn(
        "cortex_manager_lock_is_held && echo HELD || echo FREE",
        tmp_path,
        requires="cortex_manager_lock_is_held",
        extra_env={"PSC_CONTROL_ROOT": str(control_root)},
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "FREE"


def test_manager_lock_reports_free_when_file_is_absent(tmp_path: Path) -> None:
    completed = _run_start_fn(
        "cortex_manager_lock_is_held && echo HELD || echo FREE",
        tmp_path,
        requires="cortex_manager_lock_is_held",
        extra_env={"PSC_CONTROL_ROOT": str(tmp_path / "nope")},
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "FREE"


def _fallback_env(tmp_path: Path, control_root: Path, **overrides: str) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "PSC_AGENTS_ROOT": str(tmp_path / "agents"),
        "PSC_CONTROL_ROOT": str(control_root),
        "PY_LOG": str(tmp_path / "py.log"),
        "SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        "SHOW_ENV_STATUS": "1",  # systemctl --user 連不上 bus
        "FAKE_SLEEP": "5",
        "PSC_MONITOR_PROC_PATTERN": f"psc-monitor-probe-{tmp_path.name}",
    }
    env.update(overrides)
    return env


# 收尾前留一段窗口讓剛 spawn 的假子進程把自己寫進 PY_LOG，否則 kill 會跑在
# fork/exec 前面，log 永遠是空的。
_REPORT_PIDS = (
    'printf "rc=%s manager=%s monitor=%s\\n" "$rc" '
    '"${CORTEX_MANAGER_PID:-unset}" "${CORTEX_MONITOR_PID:-unset}"; '
    "sleep 0.5; "
    'for p in "${CORTEX_MANAGER_PID:-}" "${CORTEX_MONITOR_PID:-}"; do '
    '[[ -n "$p" ]] && kill "$p" 2>/dev/null; done; true'
)


def test_fallback_skips_manager_when_lock_is_already_held(
    tmp_path: Path, held_manager_lock: Path
) -> None:
    """已有常駐 manager 時，fallback 不得重起 daemon，也不得把它當成啟動失敗。"""

    bin_dir = tmp_path / "bin"
    py = tmp_path / "fake" / "python"
    _write_fake_py(py)
    _write_fake_systemctl(bin_dir / "systemctl")

    completed = _run_start_fn(
        f"rc=0; ensure_cortex_services || rc=$?; {_REPORT_PIDS}",
        tmp_path,
        requires="ensure_cortex_services",
        bin_dir=bin_dir,
        extra_env=_fallback_env(tmp_path, held_manager_lock, PY=str(py), REPO=str(REPO_ROOT)),
    )

    assert completed.returncode == 0, completed.stderr
    assert "rc=0 " in completed.stdout, completed.stdout
    assert "manager=unset" in completed.stdout, completed.stdout

    # monitor 這筆代表 fallback 已走完 spawn 階段，此時 manager 那筆仍缺席才有意義
    py_log = _await_log_entry(tmp_path / "py.log", "paulsha_cortex.cli monitor")
    assert "coordinator.manager_daemon" not in py_log, f"fallback 仍重起了 manager daemon：{py_log}"


def test_fallback_still_starts_manager_when_lock_is_free(tmp_path: Path) -> None:
    control_root = tmp_path / "control"
    control_root.mkdir()
    bin_dir = tmp_path / "bin"
    py = tmp_path / "fake" / "python"
    _write_fake_py(py)
    _write_fake_systemctl(bin_dir / "systemctl")

    completed = _run_start_fn(
        f"rc=0; ensure_cortex_services || rc=$?; {_REPORT_PIDS}",
        tmp_path,
        requires="ensure_cortex_services",
        bin_dir=bin_dir,
        extra_env=_fallback_env(tmp_path, control_root, PY=str(py), REPO=str(REPO_ROOT)),
    )

    assert completed.returncode == 0, completed.stderr
    assert "rc=0 " in completed.stdout, completed.stdout
    assert "manager=unset" not in completed.stdout, completed.stdout

    _await_log_entry(tmp_path / "py.log", "coordinator.manager_daemon")


def test_cockpit_gate_fails_when_started_manager_died(tmp_path: Path) -> None:
    """真的起不來仍要 fail-closed，不能被『已有常駐』的新分支吃掉。"""

    completed = _run_start_fn(
        "sleep 0.1 & CORTEX_MANAGER_PID=$!; sleep 0.6; "
        "rc=0; verify_cortex_fallback_alive || rc=$?; printf 'rc=%s\\n' \"$rc\"",
        tmp_path,
        requires="verify_cortex_fallback_alive",
    )

    assert completed.stdout.strip() == "rc=1", completed.stdout
    assert "cortex fallback manager exited before cockpit start" in completed.stderr


def test_cockpit_gate_fails_when_started_monitor_died(tmp_path: Path) -> None:
    completed = _run_start_fn(
        "sleep 0.1 & CORTEX_MONITOR_PID=$!; sleep 0.6; "
        "rc=0; verify_cortex_fallback_alive || rc=$?; printf 'rc=%s\\n' \"$rc\"",
        tmp_path,
        requires="verify_cortex_fallback_alive",
    )

    assert completed.stdout.strip() == "rc=1", completed.stdout
    assert "cortex fallback monitor exited before cockpit start" in completed.stderr


def test_cockpit_gate_passes_when_fallback_skipped_both(tmp_path: Path) -> None:
    """PID 未設代表 fallback 刻意跳過（systemd 已在跑），gate 不得判成失敗。"""

    completed = _run_start_fn(
        "rc=0; verify_cortex_fallback_alive || rc=$?; printf 'rc=%s\\n' \"$rc\"",
        tmp_path,
        requires="verify_cortex_fallback_alive",
    )

    assert completed.stdout.strip() == "rc=0", completed.stdout
    assert completed.stderr == ""


def test_cockpit_gate_passes_when_started_processes_alive(tmp_path: Path) -> None:
    completed = _run_start_fn(
        "sleep 5 & CORTEX_MANAGER_PID=$!; sleep 5 & CORTEX_MONITOR_PID=$!; "
        "rc=0; verify_cortex_fallback_alive || rc=$?; printf 'rc=%s\\n' \"$rc\"; "
        'kill "$CORTEX_MANAGER_PID" "$CORTEX_MONITOR_PID" 2>/dev/null; true',
        tmp_path,
        requires="verify_cortex_fallback_alive",
    )

    assert completed.stdout.strip() == "rc=0", completed.stdout


def test_start_sh_uses_extracted_cockpit_gate() -> None:
    src = START_SH.read_text(encoding="utf-8")
    assert "verify_cortex_fallback_alive || exit 1" in src


def test_fallback_skips_monitor_when_one_is_already_running(tmp_path: Path) -> None:
    """fallback monitor 沒有 single-instance 保護，起第二個會與既有 monitor 搶同一份 state。"""

    control_root = tmp_path / "control"
    control_root.mkdir()
    bin_dir = tmp_path / "bin"
    py = tmp_path / "fake" / "python"
    _write_fake_py(py)
    _write_fake_systemctl(bin_dir / "systemctl")
    pattern = f"psc-monitor-probe-{tmp_path.name}"
    probe = subprocess.Popen(["/usr/bin/bash", "-c", f'exec -a "{pattern}" sleep 30'])
    try:
        completed = _run_start_fn(
            f"rc=0; ensure_cortex_services || rc=$?; {_REPORT_PIDS}",
            tmp_path,
            requires="ensure_cortex_services",
            bin_dir=bin_dir,
            extra_env=_fallback_env(tmp_path, control_root, PY=str(py), REPO=str(REPO_ROOT)),
        )
    finally:
        probe.terminate()
        probe.wait(timeout=10)

    assert completed.returncode == 0, completed.stderr
    assert "rc=0 " in completed.stdout, completed.stdout
    assert "monitor=unset" in completed.stdout, completed.stdout

    # manager 這筆代表 fallback 已走完 spawn 階段，此時 monitor 那筆仍缺席才有意義
    py_log = _await_log_entry(tmp_path / "py.log", "coordinator.manager_daemon")
    assert "paulsha_cortex.cli monitor" not in py_log, f"fallback 仍重起了 monitor：{py_log}"
