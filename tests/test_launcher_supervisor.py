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


class _FakePopen:
    """假 Popen：模擬 spawn 後已經退出的子程序（#346）。"""

    def __init__(self, *, exit_code: int | None = 1, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode = exit_code
        self._exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int | None:
        return self._exit_code

    def kill(self) -> None:
        self.killed = True


def test_ensure_cortex_degrades_when_fallback_manager_exits_before_startup(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346: fallback manager 起了就死，ensure_cortex 不得 raise，改記 degraded。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))
    monkeypatch.setattr(supervisor, "_monitor_is_running", lambda: True)
    monkeypatch.setattr(supervisor, "_manager_lock_is_held", lambda: False)

    def fake_spawn(self, name, cmd, *, log_name, extra_env=None):
        return _FakePopen()

    monkeypatch.setattr(supervisor.Supervisor, "_spawn_service", fake_spawn)

    sup = supervisor.Supervisor()
    sup.ensure_cortex()

    assert any(
        "cortex fallback manager daemon exited before startup" in msg for msg in sup.degraded
    )
    err = capsys.readouterr().err
    assert "cortex fallback manager daemon exited before startup" in err
    assert "cortex-manager.log" in err


def test_ensure_cortex_degrades_when_fallback_monitor_exits_before_startup(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346: fallback monitor 起了就死，ensure_cortex 不得 raise，改記 degraded。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))
    monkeypatch.setattr(supervisor, "_monitor_is_running", lambda: False)
    monkeypatch.setattr(supervisor, "_manager_lock_is_held", lambda: True)

    def fake_spawn(self, name, cmd, *, log_name, extra_env=None):
        return _FakePopen()

    monkeypatch.setattr(supervisor.Supervisor, "_spawn_service", fake_spawn)

    sup = supervisor.Supervisor()
    sup.ensure_cortex()

    assert any("cortex fallback monitor exited before startup" in msg for msg in sup.degraded)
    err = capsys.readouterr().err
    assert "cortex fallback monitor exited before startup" in err
    assert "cortex-monitor.log" in err


def test_verify_cortex_fallback_alive_degrades_instead_of_raising(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346: cockpit 前把關發現 fallback manager 已死，改記 degraded、不 raise。"""
    agents_root = tmp_path / "agents"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))

    sup = supervisor.Supervisor()
    sup.manager = _FakePopen()

    sup.verify_cortex_fallback_alive()

    assert any("cortex fallback manager exited before cockpit start" in msg for msg in sup.degraded)
    err = capsys.readouterr().err
    assert "cortex fallback manager exited before cockpit start" in err
    assert "cortex-manager.log" in err


def test_run_still_launches_cockpit_when_fallback_manager_died(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346: fallback manager 啟動前就死，run() 仍要起 cockpit（degraded 而非 fail-closed）。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    monkeypatch.setattr(supervisor, "ensure_xdg_runtime_dir", lambda: None)
    monkeypatch.setattr(supervisor.Supervisor, "acquire_start_lock", lambda self: None)
    monkeypatch.setattr(supervisor, "load_default_telegram_env", lambda: None)
    monkeypatch.setattr(supervisor, "telegram_gate", lambda: False)
    monkeypatch.setattr(supervisor, "apply_stage8_footer", lambda: None)
    monkeypatch.setattr(supervisor.Supervisor, "start_cost_loop", lambda self: None)
    monkeypatch.setattr(supervisor.Supervisor, "start_dream", lambda self: None)
    monkeypatch.setattr(supervisor.time, "sleep", lambda *_args, **_kwargs: None)

    def fake_ensure_cortex(self) -> None:
        self.manager = _FakePopen()

    monkeypatch.setattr(supervisor.Supervisor, "ensure_cortex", fake_ensure_cortex)

    cockpit_calls: list[bool] = []

    def fake_run_cockpit(self) -> int:
        cockpit_calls.append(True)
        return 0

    monkeypatch.setattr(supervisor.Supervisor, "run_cockpit", fake_run_cockpit)

    exit_code = supervisor.run()

    assert exit_code == 0
    assert cockpit_calls == [True]
    err = capsys.readouterr().err
    assert "exited before cockpit start" in err
    assert "degraded" in err


def test_run_prints_degraded_summary_when_cockpit_is_terminated(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346: SIGTERM 接管時 run_cockpit 走 SystemExit(143)，degraded 摘要仍要印出來。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))

    monkeypatch.setattr(supervisor, "ensure_xdg_runtime_dir", lambda: None)
    monkeypatch.setattr(supervisor.Supervisor, "acquire_start_lock", lambda self: None)
    monkeypatch.setattr(supervisor, "load_default_telegram_env", lambda: None)
    monkeypatch.setattr(supervisor, "telegram_gate", lambda: False)
    monkeypatch.setattr(supervisor, "apply_stage8_footer", lambda: None)
    monkeypatch.setattr(supervisor.Supervisor, "start_cost_loop", lambda self: None)
    monkeypatch.setattr(supervisor.Supervisor, "start_dream", lambda self: None)
    monkeypatch.setattr(supervisor.time, "sleep", lambda *_args, **_kwargs: None)

    def fake_ensure_cortex(self) -> None:
        self.manager = _FakePopen()

    monkeypatch.setattr(supervisor.Supervisor, "ensure_cortex", fake_ensure_cortex)

    def fake_run_cockpit(self) -> int:
        raise SystemExit(143)

    monkeypatch.setattr(supervisor.Supervisor, "run_cockpit", fake_run_cockpit)

    exit_code = supervisor.run()

    assert exit_code == 143
    err = capsys.readouterr().err
    assert "本次為 degraded 啟動" in err
    assert "exited before cockpit start" in err


def test_ensure_cortex_then_verify_does_not_double_count_dead_fallback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346 對抗審查 MINOR2：ensure_cortex 已記過的死 fallback，verify 不得再記一次。"""
    agents_root = tmp_path / "agents"
    control_root = agents_root / "control"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(control_root))
    monkeypatch.setattr(supervisor, "_monitor_is_running", lambda: False)
    monkeypatch.setattr(supervisor, "_manager_lock_is_held", lambda: False)

    def fake_spawn(self, name, cmd, *, log_name, extra_env=None):
        child = _FakePopen()
        self.children[name] = child
        return child

    monkeypatch.setattr(supervisor.Supervisor, "_spawn_service", fake_spawn)

    sup = supervisor.Supervisor()
    sup.ensure_cortex()
    assert len(sup.degraded) == 2  # monitor + manager 各記一次

    sup.verify_cortex_fallback_alive()

    assert len(sup.degraded) == 2  # 不得再重覆記錄同一組死掉的 fallback
    assert sup.children.get("cortex-monitor") is None
    assert sup.manager is None


def test_note_degraded_message_reflects_no_cockpit_mode(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#346 對抗審查 MINOR3：--no-cockpit 下訊息不得宣稱 cockpit 仍會啟動。"""
    agents_root = tmp_path / "agents"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))

    sup = supervisor.Supervisor(no_cockpit=True)
    sup._note_degraded("test message", log_name="cortex-manager.log")

    err = capsys.readouterr().err
    assert "--no-cockpit" in err
    assert "cockpit 仍照常啟動" not in err
