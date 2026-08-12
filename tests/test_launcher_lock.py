"""launcher.lock 單元測試（#288 C 節）。

隔離守則：所有案例把 lock 檔放在 tmp（PSC_START_LOCK 或顯式路徑）、systemctl
一律注入 recording fake runner——絕不碰真機 start lock、絕不呼叫真 systemctl。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from paulshaclaw.launcher import lock


REPO_ROOT = Path(__file__).resolve().parents[1]


class RecordingRunner:
    """記錄 stop 呼叫的 fake systemctl runner；可掛 side effect。"""

    def __init__(self, side_effect=None) -> None:
        self.calls: list[list[str]] = []
        self.side_effect = side_effect

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        if self.side_effect is not None:
            self.side_effect(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0, "", "")


def _spawn_bash_holder(lock_path: Path, *, sig_ign: bool = False) -> subprocess.Popen:
    """以 start.sh 同款協議持鎖的 bash 子行程；印 ready 後常駐等 TERM。"""
    trap_line = "trap '' TERM" if sig_ign else "trap 'exit 0' TERM"
    # `sleep &` 需 200>&-：背景子行程會繼承 fd 200，bash 死了鎖仍被 sleep 持有
    #（正是 start.sh bot supervisor 修 200>&- 的同一坑）。
    script = f"""
exec 200>>"$1"
flock -n 200 || exit 9
{trap_line}
echo ready
sleep 60 200>&- &
wait $!
"""
    proc = subprocess.Popen(
        ["/usr/bin/bash", "-c", script, "bash", str(lock_path)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    assert line == "ready", f"holder 未就緒：{line!r}"
    return proc


def _write_process_holder_meta(lock_path: Path, pid: int, holder: str = "dev") -> None:
    meta = lock.build_holder_meta(
        holder=holder,
        pid=pid,
        stop={"kind": "process", "pid": pid},
        version="test",
    )
    lock.write_holder(lock_path, meta)


def _cleanup_holder(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)
    if proc.stdout is not None:
        proc.stdout.close()


# ---------------------------------------------------------------------------
# default_lock_path 三層 fallback
# ---------------------------------------------------------------------------


def test_default_lock_path_prefers_psc_start_lock(tmp_path, monkeypatch) -> None:
    override = tmp_path / "my.lock"
    monkeypatch.setenv("PSC_START_LOCK", str(override))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    assert lock.default_lock_path() == override


def test_default_lock_path_uses_xdg_runtime_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PSC_START_LOCK", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert lock.default_lock_path() == tmp_path / "paulshaclaw-start.lock"


def test_default_lock_path_falls_back_to_tmp(monkeypatch) -> None:
    monkeypatch.delenv("PSC_START_LOCK", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    # /run/user/<uid> 不存在 → 落到 /tmp（鏡射 ensure_xdg_runtime_dir 規則）。
    monkeypatch.setattr(lock.os, "getuid", lambda: 999_999_999)
    assert lock.default_lock_path() == Path("/tmp/paulshaclaw-start.lock")


# ---------------------------------------------------------------------------
# metadata roundtrip 與 corrupt fail-closed
# ---------------------------------------------------------------------------


def test_holder_metadata_roundtrip(tmp_path) -> None:
    lock_path = tmp_path / "start.lock"
    meta = lock.build_holder_meta(
        holder="release",
        pid=os.getpid(),
        stop={"kind": "systemd", "unit": "demo-telegram.service"},
        version="0.1.0",
    )
    lock.write_holder(lock_path, meta)
    loaded = lock.read_holder(lock_path)
    assert loaded is not None
    assert loaded["schema"] == lock.SCHEMA_VERSION
    assert loaded["holder"] == "release"
    assert loaded["stop"] == {"kind": "systemd", "unit": "demo-telegram.service"}
    assert loaded["version"] == "0.1.0"
    assert loaded["pid"] == os.getpid()


def test_read_holder_returns_none_for_corrupt_or_empty(tmp_path) -> None:
    lock_path = tmp_path / "start.lock"
    assert lock.read_holder(lock_path) is None  # 不存在
    lock_path.write_text("", encoding="utf-8")
    assert lock.read_holder(lock_path) is None  # 空檔
    lock_path.write_text("not-json {", encoding="utf-8")
    assert lock.read_holder(lock_path) is None  # corrupt


def test_takeover_fails_closed_on_held_lock_without_readable_metadata(tmp_path) -> None:
    """持有中但 metadata corrupt：不盲殺、TakeoverError fail-closed。"""
    lock_path = tmp_path / "start.lock"
    proc = _spawn_bash_holder(lock_path)
    try:
        lock_path.write_text("garbage", encoding="utf-8")
        runner = RecordingRunner()
        with pytest.raises(lock.TakeoverError):
            lock.takeover(lock_path, timeout=1, runner=runner)
        # 持有者必須毫髮無傷（沒有被盲殺）。
        assert proc.poll() is None
    finally:
        _cleanup_holder(proc)


# ---------------------------------------------------------------------------
# HeldLock
# ---------------------------------------------------------------------------


def test_held_lock_acquire_writes_meta_and_release_frees(tmp_path) -> None:
    lock_path = tmp_path / "start.lock"
    meta = lock.build_holder_meta(
        holder="release",
        pid=os.getpid(),
        stop={"kind": "process", "pid": os.getpid()},
        version="test",
    )
    held = lock.HeldLock(lock_path, meta)
    held.acquire()
    try:
        assert lock.read_holder(lock_path)["holder"] == "release"
        second = lock.HeldLock(lock_path, meta)
        with pytest.raises(lock.LockHeldError):
            second.acquire()
        assert lock.status(lock_path)["held"] is True
    finally:
        held.release()
    assert lock.status(lock_path)["held"] is False


# ---------------------------------------------------------------------------
# takeover：process 持有者
# ---------------------------------------------------------------------------


def test_takeover_stops_process_holder_with_sigterm(tmp_path) -> None:
    lock_path = tmp_path / "start.lock"
    proc = _spawn_bash_holder(lock_path)
    try:
        _write_process_holder_meta(lock_path, proc.pid)
        runner = RecordingRunner()
        report = lock.takeover(lock_path, timeout=10, runner=runner)
        assert report["status"] == "taken-over"
        assert report["holder"]["stop"] == {"kind": "process", "pid": proc.pid}
        assert proc.wait(timeout=10) == 0  # TERM 後乾淨退出、鎖釋放
        assert lock.status(lock_path)["held"] is False
    finally:
        _cleanup_holder(proc)


def test_takeover_times_out_fail_closed_on_sigign_holder(tmp_path) -> None:
    """SIG_IGN 持有者：逾時 TakeoverError，且不升級為 KILL（不盲殺）。"""
    lock_path = tmp_path / "start.lock"
    proc = _spawn_bash_holder(lock_path, sig_ign=True)
    try:
        _write_process_holder_meta(lock_path, proc.pid)
        runner = RecordingRunner()
        with pytest.raises(lock.TakeoverError) as excinfo:
            lock.takeover(lock_path, timeout=1, runner=runner)
        assert excinfo.value.holder is not None
        assert proc.poll() is None  # 沒被 KILL
        assert lock.status(lock_path)["held"] is True
    finally:
        _cleanup_holder(proc)


# ---------------------------------------------------------------------------
# takeover：systemd 持有者
# ---------------------------------------------------------------------------


def test_takeover_stops_systemd_holder_via_systemctl(tmp_path) -> None:
    """systemd 持有者必須走 systemctl --user stop（直接 kill 會被 Restart 拉回）。"""
    lock_path = tmp_path / "start.lock"
    proc = _spawn_bash_holder(lock_path)
    try:
        meta = lock.build_holder_meta(
            holder="release",
            pid=proc.pid,
            stop={"kind": "systemd", "unit": "demo-telegram.service"},
            version="test",
        )
        lock.write_holder(lock_path, meta)

        def stop_unit(cmd: list[str]) -> None:
            if cmd[-1] == "demo-telegram.service":
                proc.terminate()  # 模擬 systemctl 停掉該 unit

        runner = RecordingRunner(side_effect=stop_unit)
        report = lock.takeover(lock_path, timeout=10, runner=runner)
        assert report["status"] == "taken-over"
        assert ["systemctl", "--user", "stop", "demo-telegram.service"] in runner.calls
        # 持有者 pid 沒有被本行程 kill——停法是 systemctl，不是 signal。
        assert report["stop_action"] == "systemctl --user stop demo-telegram.service"
    finally:
        _cleanup_holder(proc)


# ---------------------------------------------------------------------------
# 操作面 unit 白名單（cortex / hippo 邊界）
# ---------------------------------------------------------------------------


def test_stop_operator_units_whitelist_only_cost_and_telegram(monkeypatch) -> None:
    monkeypatch.delenv("PSC_OPERATOR_INSTANCE", raising=False)
    runner = RecordingRunner()
    actions = lock.stop_operator_units(runner=runner)
    stopped = [call[-1] for call in runner.calls]
    assert stopped == ["paulshaclaw-cost.service", "paulshaclaw-telegram.service"]
    assert len(actions) == 2
    joined = " ".join(" ".join(call) for call in runner.calls)
    for forbidden in ("cortex-manager", "cortex-monitor", "hippo"):
        assert forbidden not in joined


def test_operator_unit_names_reject_governance_instance(monkeypatch) -> None:
    """誤設 instance 指向治理面（如 PSC_INSTANCE 語意的 cortex）必須 fail-closed。"""
    monkeypatch.setenv("PSC_OPERATOR_INSTANCE", "cortex")
    with pytest.raises(lock.TakeoverError):
        lock.operator_unit_names()


def test_takeover_rejects_governance_unit_in_holder_metadata(tmp_path) -> None:
    lock_path = tmp_path / "start.lock"
    proc = _spawn_bash_holder(lock_path)
    try:
        meta = lock.build_holder_meta(
            holder="release",
            pid=proc.pid,
            stop={"kind": "systemd", "unit": "cortex-manager.service"},
            version="test",
        )
        lock.write_holder(lock_path, meta)
        runner = RecordingRunner()
        with pytest.raises(lock.TakeoverError):
            lock.takeover(lock_path, timeout=1, runner=runner)
        # 治理面 unit 絕不出現在 stop 呼叫中。
        assert all("cortex-manager" not in " ".join(call) for call in runner.calls)
        assert proc.poll() is None
    finally:
        _cleanup_holder(proc)


# ---------------------------------------------------------------------------
# timeout 覆寫
# ---------------------------------------------------------------------------


def test_takeover_timeout_env_override(monkeypatch) -> None:
    monkeypatch.delenv("PSC_TAKEOVER_TIMEOUT_SECONDS", raising=False)
    assert lock._resolve_timeout(None) == lock.DEFAULT_TAKEOVER_TIMEOUT_SECONDS
    monkeypatch.setenv("PSC_TAKEOVER_TIMEOUT_SECONDS", "7.5")
    assert lock._resolve_timeout(None) == 7.5
    assert lock._resolve_timeout(3) == 3.0
