"""雙向接管整合測試（#288 C 節驗收）。

dev（start.sh 協議）↔ release（HeldLock / takeover CLI）兩個方向都要能
「後起的為主」。隔離：lock 檔在 tmp、fake systemctl 前置 PATH——絕不碰真機
start lock 與真 systemd。
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from paulshaclaw.launcher import lock

REPO_ROOT = Path(__file__).resolve().parents[1]
START_SH = REPO_ROOT / "scripts" / "start.sh"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0, "", "")


@pytest.fixture()
def fake_systemctl(tmp_path: Path) -> tuple[Path, Path]:
    """fake systemctl 目錄與呼叫 log（給 subprocess 型接管用）。"""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "systemctl.log"
    script = bin_dir / "systemctl"
    script.write_text(
        f"#!/bin/bash\nprintf '%s\\n' \"systemctl $*\" >> \"{log}\"\nexit 0\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir, log


def _subprocess_env(bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return env


def _cleanup(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()


def _spawn_dev_style_holder(lock_path: Path, env: dict[str, str]) -> subprocess.Popen:
    """以 start.sh 同款協議持鎖：exec 200>>、flock -n、真 write-holder CLI、trap TERM。"""
    script = textwrap.dedent(
        """
        exec 200>>"$1"
        flock -n 200 || exit 9
        "$2" -m paulshaclaw.launcher.lock write-holder \
          --lock-file "$1" --holder dev --pid $$ --source "$3" || exit 8
        trap 'exit 0' TERM
        echo ready
        sleep 60 200>&- &
        wait $!
        """
    )
    proc = subprocess.Popen(
        ["/usr/bin/bash", "-c", script, "bash", str(lock_path), sys.executable, str(REPO_ROOT)],
        stdout=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    assert line == "ready", f"dev holder 未就緒：{line!r}"
    return proc


def test_dev_holder_taken_over_by_release_path(tmp_path, fake_systemctl) -> None:
    """(a) dev→release：paulshaclaw up 的同一條 takeover 路徑停掉 start.sh 持有者。"""
    bin_dir, _log = fake_systemctl
    lock_path = tmp_path / "start.lock"
    proc = _spawn_dev_style_holder(lock_path, _subprocess_env(bin_dir))
    try:
        holder_before = lock.read_holder(lock_path)
        assert holder_before is not None and holder_before["holder"] == "dev"

        runner = RecordingRunner()
        report = lock.takeover(lock_path, timeout=15, runner=runner)

        assert report["status"] == "taken-over"
        assert proc.wait(timeout=10) == 0  # dev 持有者被 TERM 後乾淨退出

        # 新持有者以 release 身分上鎖，metadata 換人。
        meta = lock.build_holder_meta(
            holder="release",
            pid=os.getpid(),
            stop={"kind": "process", "pid": os.getpid()},
            version="test-release",
        )
        with lock.HeldLock(lock_path, meta):
            assert lock.read_holder(lock_path)["holder"] == "release"
    finally:
        _cleanup(proc)


def test_release_holder_taken_over_by_dev_cli_path(tmp_path, fake_systemctl) -> None:
    """(b) release→dev：start.sh 同款 CLI takeover 停掉 HeldLock（release）持有者。"""
    bin_dir, log = fake_systemctl
    lock_path = tmp_path / "start.lock"
    holder_code = textwrap.dedent(
        """
        import os
        import signal
        import sys

        from paulshaclaw.launcher import lock

        meta = lock.build_holder_meta(
            holder="release",
            pid=os.getpid(),
            stop={"kind": "process", "pid": os.getpid()},
            version="test-release",
        )
        held = lock.HeldLock(sys.argv[1], meta)
        held.acquire()
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        print("ready", flush=True)
        while True:
            signal.pause()
        """
    )
    env = _subprocess_env(bin_dir)
    proc = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(lock_path)],
        stdout=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "ready"
        assert lock.read_holder(lock_path)["holder"] == "release"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paulshaclaw.launcher.lock",
                "takeover",
                "--lock-file",
                str(lock_path),
                "--timeout",
                "15",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout)["status"] == "taken-over"
        assert proc.wait(timeout=10) == 0

        # bash flock -n 證明鎖已可取（dev 路徑接手）。
        flock_probe = subprocess.run(
            ["/usr/bin/flock", "-n", str(lock_path), "true"], check=False
        )
        assert flock_probe.returncode == 0
        # fake systemctl 有收到操作面 stop（且僅止於操作面）。
        log_text = log.read_text(encoding="utf-8")
        assert "stop paulshaclaw-cost.service" in log_text
        assert "stop paulshaclaw-telegram.service" in log_text
        assert "cortex" not in log_text and "hippo" not in log_text
    finally:
        _cleanup(proc)


def test_unstoppable_holder_fails_closed_with_holder_report(
    tmp_path, fake_systemctl
) -> None:
    """(c) SIG_IGN 持有者：CLI 非零退出且輸出含持有者報告，不盲殺不並存。"""
    bin_dir, _log = fake_systemctl
    lock_path = tmp_path / "start.lock"
    script = textwrap.dedent(
        """
        exec 200>>"$1"
        flock -n 200 || exit 9
        "$2" -m paulshaclaw.launcher.lock write-holder \
          --lock-file "$1" --holder dev --pid $$ --source "$3" || exit 8
        trap '' TERM
        echo ready
        sleep 60
        """
    )
    env = _subprocess_env(bin_dir)
    proc = subprocess.Popen(
        ["/usr/bin/bash", "-c", script, "bash", str(lock_path), sys.executable, str(REPO_ROOT)],
        stdout=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "ready"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paulshaclaw.launcher.lock",
                "takeover",
                "--lock-file",
                str(lock_path),
                "--timeout",
                "1",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode != 0
        assert "takeover failed" in completed.stderr
        assert '"holder": "dev"' in completed.stderr  # 持有者報告
        assert proc.poll() is None  # 沒被 KILL，兩套並存被 fail-closed 阻止
    finally:
        _cleanup(proc)


def test_start_sh_uses_shared_takeover_protocol() -> None:
    """(d) 靜態斷言：start.sh 已切到共用 takeover 協議。"""
    src = START_SH.read_text(encoding="utf-8")
    assert "launcher.lock takeover" in src
    assert "exec 200>>" in src
    assert "launcher.lock write-holder" in src
    assert 'flock -n 200 || { echo 已有實例在跑; exit 1; }' not in src
    # PSC_START_LOCK 覆寫點與 timeout 覆寫點存在。
    assert 'PSC_START_LOCK' in src
    assert 'PSC_TAKEOVER_TIMEOUT_SECONDS:-30' in src
    # bot supervisor subshell 不得繼承 lock fd（孤兒持鎖防護）。
    assert ") 200>&- &" in src
