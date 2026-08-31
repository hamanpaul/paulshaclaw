"""launcher.supervisor 單元測試（#288 A 節、#334 啟動路徑與 lock 探測）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from paulshaclaw.launcher import supervisor

REPO_ROOT = Path(__file__).resolve().parents[1]


class _LockHolder:
    """在背景進程中持有 lock 檔的 flock。"""

    def __init__(self, lock_path: Path) -> None:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
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
        line = self._proc.stdout.readline().strip()
        assert line == "locked", f"lock holder 未就緒: {line!r}"

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=10)
        if self._proc.stdout is not None:
            self._proc.stdout.close()


def test_manager_lock_reports_held_when_cortex_subpath_lock_is_held(
    tmp_path: Path, monkeypatch
) -> None:
    """#334: cortex-manager 持有 control/cortex/manager.lock 時，探測必須回報 held。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    cortex_lock = control_root / "cortex" / "manager.lock"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    holder = _LockHolder(cortex_lock)
    try:
        assert supervisor._manager_lock_is_held() is True
    finally:
        holder.close()


def test_manager_lock_reports_free_when_cortex_subpath_lock_is_stale(
    tmp_path: Path, monkeypatch
) -> None:
    """#334: control/cortex/manager.lock 存在但無 flock 持有（stale），探測必須回報 free。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    cortex_lock = control_root / "cortex" / "manager.lock"
    cortex_lock.parent.mkdir(parents=True, exist_ok=True)
    cortex_lock.write_text("12345\n", encoding="utf-8")
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    assert supervisor._manager_lock_is_held() is False


def test_manager_lock_reports_held_when_legacy_flat_lock_is_held(
    tmp_path: Path, monkeypatch
) -> None:
    """#334: legacy flat control/manager.lock 被持有且 nested lock 不存在時，探測必須回報 held。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    legacy_lock = control_root / "manager.lock"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    holder = _LockHolder(legacy_lock)
    try:
        assert supervisor._manager_lock_is_held() is True
    finally:
        holder.close()


def test_manager_lock_reports_free_when_legacy_flat_lock_is_stale(
    tmp_path: Path, monkeypatch
) -> None:
    """#334: legacy flat control/manager.lock 存在但無 flock 持有（stale），探測必須回報 free。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    legacy_lock = control_root / "manager.lock"
    legacy_lock.parent.mkdir(parents=True, exist_ok=True)
    legacy_lock.write_text("12345\n", encoding="utf-8")
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    assert supervisor._manager_lock_is_held() is False


def test_manager_lock_reports_free_when_no_locks_exist(
    tmp_path: Path, monkeypatch
) -> None:
    """#334: 兩個 lock 檔皆不存在時，探測必須回報 free。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    assert supervisor._manager_lock_is_held() is False


def test_manager_lock_reports_free_on_non_blocking_oserror(
    tmp_path: Path, monkeypatch
) -> None:
    """非 EWOULDBLOCK 的 flock 錯誤不得被誤判成 held。"""
    lock_path = tmp_path / "manager.lock"
    lock_path.write_text("", encoding="utf-8")

    def raise_io_error(*args, **kwargs):
        raise OSError("simulated flock failure")

    monkeypatch.setattr(supervisor.fcntl, "flock", raise_io_error)

    assert supervisor._lock_file_is_held(lock_path) is False


def test_supervisor_ensure_cortex_skips_when_cortex_subpath_lock_is_held(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#334: cortex manager lock 被持有時，ensure_cortex 不得啟動 fallback manager。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    cortex_lock = control_root / "cortex" / "manager.lock"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))
    monkeypatch.setattr(supervisor, "_monitor_is_running", lambda: True)

    holder = _LockHolder(cortex_lock)
    sup = supervisor.Supervisor()
    try:
        try:
            sup.ensure_cortex()
            assert sup.manager is None
            err = capsys.readouterr().err
            assert "cortex manager 已在運行" in err
        finally:
            sup.shutdown()
    finally:
        holder.close()


def test_supervisor_ensure_cortex_skips_when_legacy_flat_lock_is_held(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#334: legacy flat manager lock 被持有時，ensure_cortex 亦不得啟動 fallback manager。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    legacy_lock = control_root / "manager.lock"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))
    monkeypatch.setattr(supervisor, "_monitor_is_running", lambda: True)

    holder = _LockHolder(legacy_lock)
    sup = supervisor.Supervisor()
    try:
        try:
            sup.ensure_cortex()
            assert sup.manager is None
            err = capsys.readouterr().err
            assert "cortex manager 已在運行" in err
        finally:
            sup.shutdown()
    finally:
        holder.close()
