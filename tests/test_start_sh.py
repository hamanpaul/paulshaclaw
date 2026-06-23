from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_SH = PROJECT_ROOT / "scripts" / "start.sh"


FAKE_PYTHON = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    from __future__ import annotations

    import os
    import signal
    import sys
    import time
    from pathlib import Path


    def _module_name(argv: list[str]) -> str | None:
        if len(argv) >= 3 and argv[1] == "-m":
            return argv[2]
        return None


    def main() -> int:
        module = _module_name(sys.argv)
        if len(sys.argv) >= 3 and sys.argv[1] == "-c":
            if os.environ.get("FAKE_TMUX_REFRESH_ERROR") == "1":
                return 1
            print(os.environ.get("FAKE_TMUX_REFRESH_SECONDS", "30"))
            return 0

        if module == "paulshaclaw.monitor":
            pidfile = Path(os.environ["FAKE_MONITOR_PIDFILE"])
            pidfile.write_text(str(os.getpid()), encoding="utf-8")
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            if os.environ.get("FAKE_MONITOR_MODE") == "exit":
                time.sleep(0.2)
                return 1
            signal.pause()
            return 0

        if module == "paulshaclaw.bot.listener":
            pidfile = Path(os.environ["FAKE_TELEGRAM_PIDFILE"])
            pidfile.write_text(str(os.getpid()), encoding="utf-8")
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            mode = os.environ.get("FAKE_TELEGRAM_MODE", "ready")
            if mode == "init-fail":
                time.sleep(0.2)
                return 1
            readyfile_path = os.environ.get("PSC_TELEGRAM_READY_FILE") or os.environ["FAKE_TELEGRAM_READYFILE"]
            readyfile = Path(readyfile_path)
            time.sleep(float(os.environ.get("FAKE_TELEGRAM_READY_DELAY", "0.2")))
            readyfile.write_text("ready", encoding="utf-8")
            if mode == "ready-then-die":
                time.sleep(0.2)
                return 1
            signal.pause()
            return 0

        if module == "paulshaclaw.cost.status":
            print("cdx 5h:$12.34 wk:$56.78")
            return 0

        if module == "paulshaclaw.cost":
            # Stage 8 cost-snapshot refresh loop invokes `-m paulshaclaw.cost
            # --once`; treat it as a cheap no-op success in the harness.
            return 0

        if module == "paulshaclaw.memory.cli" and sys.argv[3:6] == ["memory", "dream", "run"]:
            pidfile = Path(os.environ["FAKE_DREAM_PIDFILE"])
            pidfile.write_text(str(os.getpid()), encoding="utf-8")
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            if os.environ.get("FAKE_DREAM_MODE") == "hold":
                signal.pause()
                return 0
            return 0

        if module == "paulshaclaw.cockpit":
            Path(os.environ["FAKE_COCKPIT_STARTED"]).write_text("started", encoding="utf-8")
            Path(os.environ["FAKE_COCKPIT_PIDFILE"]).write_text(str(os.getpid()), encoding="utf-8")
            if os.environ.get("FAKE_COCKPIT_MODE") == "exit":
                for pidfile_name in ("FAKE_MONITOR_PIDFILE", "FAKE_TELEGRAM_PIDFILE"):
                    pidfile_path = os.environ.get(pidfile_name)
                    if not pidfile_path:
                        continue
                    pidfile = Path(pidfile_path)
                    deadline = time.monotonic() + 5.0
                    while time.monotonic() < deadline:
                        if pidfile.exists() and pidfile.read_text(encoding="utf-8").strip():
                            break
                        time.sleep(0.02)
                return 0
            signal.pause()
            return 0

        print(f"unexpected argv: {sys.argv!r}", file=sys.stderr)
        return 2


    if __name__ == "__main__":
        raise SystemExit(main())
    """
)

FAKE_TMUX = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    from __future__ import annotations

    import json
    import os
    import sys
    from pathlib import Path


    def main() -> int:
        log_path = Path(os.environ["FAKE_TMUX_LOG"])
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sys.argv[1:]) + "\\n")

        if sys.argv[1:] == ["show-option", "-qv", "status-right"]:
            value = os.environ.get("FAKE_TMUX_STATUS_RIGHT", "")
            if value:
                print(value)
            return 0

        return 0


    if __name__ == "__main__":
        raise SystemExit(main())
    """
)


class StartScriptLifecycleTests(unittest.TestCase):
    def test_paulshaclaw_module_launches_carry_pythonpath(self) -> None:
        # Regression for #92: every `python -m paulshaclaw.*` launch in start.sh
        # must export PYTHONPATH="$REPO" so the (non-editable-installed) package
        # resolves regardless of the CWD start.sh is invoked from. The
        # monitor/listener/cockpit launches historically relied on CWD being repo
        # root and died with ModuleNotFoundError when started from elsewhere
        # (e.g. `cd scripts && ./start.sh`, a systemd unit, or cron), while the
        # cost/dream loops survived only because they already set PYTHONPATH.
        text = START_SH.read_text(encoding="utf-8")
        missing = [
            line.strip()
            for line in text.splitlines()
            if "-m paulshaclaw." in line
            and not line.lstrip().startswith("#")
            and "PYTHONPATH" not in line
        ]
        self.assertEqual(
            missing,
            [],
            f"start.sh `-m paulshaclaw.*` launches missing PYTHONPATH=$REPO: {missing}",
        )

    def test_monitor_and_cockpit_start_without_telegram_inputs(self) -> None:
        self._run_lifecycle_test(cockpit_mode="exit", telegram_enabled=False, capture_output=True)

    def test_monitor_cockpit_and_telegram_ready_when_inputs_present(self) -> None:
        self._run_lifecycle_test(signal_to_wrapper=signal.SIGTERM, telegram_enabled=True, telegram_mode="ready")

    def test_token_only_fails_closed(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_token="fake-token",
            telegram_config_state="missing",
            expect_monitor_started=False,
            expect_cockpit_started=False,
            expect_returncode=1,
            capture_output=True,
        )

    def test_config_only_fails_closed(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_token=None,
            telegram_config_state="present",
            expect_monitor_started=False,
            expect_cockpit_started=False,
            expect_returncode=1,
            capture_output=True,
        )

    def test_unreadable_config_fails_closed(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_token="fake-token",
            telegram_config_state="unreadable",
            expect_monitor_started=False,
            expect_cockpit_started=False,
            expect_returncode=1,
            capture_output=True,
        )

    def test_stale_telegram_log_does_not_fake_readiness(self) -> None:
        self._run_lifecycle_test(
            signal_to_wrapper=signal.SIGTERM,
            telegram_enabled=True,
            telegram_mode="slow-ready",
            telegram_ready_delay=0.4,
            preseed_telegram_log="Telegram listener ready\n",
        )

    def test_ready_then_die_fails_closed(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_mode="ready-then-die",
            expect_cockpit_started=False,
            expect_returncode=1,
            capture_output=True,
        )

    def test_telegram_init_failure_prevents_success(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_mode="init-fail",
            expect_cockpit_started=False,
            expect_returncode=1,
        )

    def test_monitor_exit_warns_but_starts_cockpit(self) -> None:
        # 隱患 1: telegram block 內監控 monitor 死亡的兩處檢查已改為 warn-only。
        # 當 monitor 在 telegram readiness wait 之中或之後退出時，cockpit 仍應啟動，
        # 由 L191 的統一 warn 路徑提示 monitor 已終止。
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_mode="ready",
            monitor_mode="exit",
            cockpit_mode="exit",
            expect_cockpit_started=True,
            expect_returncode=0,
            capture_output=True,
        )

    def test_monitor_is_terminated_when_cockpit_receives_sigint(self) -> None:
        self._run_lifecycle_test(signal_to_wrapper=signal.SIGINT, telegram_enabled=True)

    def test_monitor_is_terminated_when_cockpit_exits_on_its_own(self) -> None:
        self._run_lifecycle_test(cockpit_mode="exit", telegram_enabled=True)

    def test_monitor_is_terminated_when_wrapper_receives_sigterm(self) -> None:
        self._run_lifecycle_test(signal_to_wrapper=signal.SIGTERM, telegram_enabled=True)

    def _run_lifecycle_test(
        self,
        *,
        cockpit_mode: str | None = None,
        signal_to_wrapper: signal.Signals | None = None,
        telegram_enabled: bool = True,
        telegram_token: str | None = "fake-token",
        telegram_config_state: str = "present",
        telegram_mode: str = "ready",
        telegram_ready_delay: float = 0.2,
        monitor_mode: str = "running",
        expect_monitor_started: bool = True,
        expect_cockpit_started: bool = True,
        expect_returncode: int | None = None,
        capture_output: bool = False,
        preseed_telegram_log: str | None = None,
    ) -> None:
        telegram_should_start = telegram_enabled and telegram_token is not None and telegram_config_state == "present"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            telegram_pidfile = tmpdir_path / "telegram.pid"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"
            stage1_config = tmpdir_path / "stage1.json"
            telegram_log = home_dir / ".agents" / "log" / "telegram.log"
            telegram_readyfile = home_dir / ".agents" / "run" / "telegram.ready"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            # Isolate tmux: a fake tmux on PATH + a private TMUX socket so the
            # real start.sh's apply_stage8_footer cannot clobber the developer's
            # live tmux status-right when the suite runs inside a tmux session.
            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh_text = START_SH.read_text(encoding="utf-8")
            self.assertIn('BASH_SOURCE[0]', start_sh_text)
            self.assertNotIn("set -m", start_sh_text)
            self.assertNotIn("while kill -0", start_sh_text)
            start_sh.write_text(start_sh_text, encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["TMUX_PANE"] = "%0"
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["TMUX"] = str(tmpdir_path / "tmux.sock")
            runtime_dir = tmpdir_path / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            env["FAKE_TMUX_LOG"] = str(tmpdir_path / "tmux.log")
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_MONITOR_MODE"] = monitor_mode
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            if telegram_enabled:
                if telegram_config_state == "present":
                    stage1_config.write_text("{}", encoding="utf-8")
                    env["PSC_STAGE1_CONFIG"] = str(stage1_config)
                elif telegram_config_state == "unreadable":
                    stage1_config.write_text("{}", encoding="utf-8")
                    stage1_config.chmod(0)
                    env["PSC_STAGE1_CONFIG"] = str(stage1_config)
                elif telegram_config_state == "missing":
                    pass
                else:
                    raise AssertionError(f"unknown telegram_config_state: {telegram_config_state}")
                if telegram_token is not None:
                    env["PSC_TELEGRAM_BOT_TOKEN"] = telegram_token
                env["FAKE_TELEGRAM_PIDFILE"] = str(telegram_pidfile)
                env["FAKE_TELEGRAM_READYFILE"] = str(telegram_readyfile)
                env["FAKE_TELEGRAM_MODE"] = telegram_mode
                env["FAKE_TELEGRAM_READY_DELAY"] = str(telegram_ready_delay)
            if cockpit_mode is not None:
                env["FAKE_COCKPIT_MODE"] = cockpit_mode

            if preseed_telegram_log is not None:
                telegram_log.parent.mkdir(parents=True, exist_ok=True)
                telegram_log.write_text(preseed_telegram_log, encoding="utf-8")

            stdout = subprocess.PIPE if capture_output else subprocess.DEVNULL
            stderr = subprocess.STDOUT if capture_output else subprocess.DEVNULL
            proc = subprocess.Popen(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                start_new_session=True,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            try:
                if not expect_monitor_started:
                    self._wait_for_missing_file(monitor_pidfile)
                if expect_monitor_started:
                    monitor_pid = self._wait_for_pidfile_int(monitor_pidfile)
                if expect_cockpit_started:
                    cockpit_pid = self._wait_for_pidfile_int(cockpit_pidfile)
                    self._wait_for_file(cockpit_started)
                else:
                    self._wait_for_missing_file(cockpit_started)
                if telegram_enabled:
                    if not telegram_should_start:
                        self._wait_for_missing_file(telegram_pidfile)
                    else:
                        telegram_pid = self._wait_for_pidfile_int(telegram_pidfile)
                        if telegram_mode == "init-fail":
                            self._wait_for_empty_file(telegram_readyfile)
                        else:
                            self._wait_for_file(telegram_readyfile)
                            if expect_cockpit_started:
                                self.assertLessEqual(telegram_readyfile.stat().st_mtime_ns, cockpit_started.stat().st_mtime_ns)
                else:
                    self._wait_for_missing_file(telegram_pidfile)

                if signal_to_wrapper is None:
                    proc.wait(timeout=10)
                else:
                    if signal_to_wrapper == signal.SIGINT:
                        os.killpg(os.getpgid(proc.pid), signal_to_wrapper)
                    else:
                        os.kill(proc.pid, signal_to_wrapper)
                    proc.wait(timeout=10)

                if expect_returncode is not None:
                    self.assertEqual(proc.returncode, expect_returncode)
                else:
                    expected_returncode = 0 if cockpit_mode == "exit" else (
                        130 if signal_to_wrapper == signal.SIGINT else 143 if signal_to_wrapper == signal.SIGTERM else proc.returncode
                    )
                    self.assertEqual(proc.returncode, expected_returncode)

                if expect_monitor_started:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(monitor_pid, 0)
                if telegram_should_start:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(telegram_pid, 0)
                if expect_cockpit_started:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(cockpit_pid, 0)

                if capture_output:
                    output = proc.communicate(timeout=10)[0]
                    if not telegram_enabled:
                        self.assertIn("telegram skipped", output)
                        self.assertNotIn("telegram pid=", output)
                    if telegram_enabled and not telegram_should_start:
                        self.assertIn("telegram startup requires both", output)
                    if telegram_should_start and telegram_mode == "init-fail":
                        self.assertIn("telegram listener exited before ready", output)
                    if monitor_mode == "exit":
                        self.assertIn("monitor exited before cockpit start", output)
                    if not expect_monitor_started:
                        self.assertNotIn("monitor pid=", output)

            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                if monitor_pidfile.exists():
                    try:
                        monitor_pid_text = monitor_pidfile.read_text(encoding="utf-8").strip()
                        if monitor_pid_text:
                            os.kill(int(monitor_pid_text), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except ValueError:
                        pass
                if telegram_pidfile.exists():
                    try:
                        telegram_pid_text = telegram_pidfile.read_text(encoding="utf-8").strip()
                        if telegram_pid_text:
                            os.kill(int(telegram_pid_text), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except ValueError:
                        pass

    def _wait_for_file(self, path: Path, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(0.05)
        self.fail(f"timed out waiting for {path}")

    def _wait_for_pidfile_int(self, path: Path, timeout: float = 8.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return int(text)
            time.sleep(0.05)
        self.fail(f"timed out waiting for non-empty pid in {path}")

    def _wait_for_missing_file(self, path: Path, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                self.fail(f"unexpected file appeared: {path}")
            time.sleep(0.05)

    def _wait_for_empty_file(self, path: Path, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and not path.read_text(encoding="utf-8").strip():
                return
            time.sleep(0.05)
        self.fail(f"timed out waiting for empty file at {path}")


class StartScriptSingletonGuardTests(unittest.TestCase):
    def _wait_for_pidfile_int(self, path: Path, timeout: float = 8.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return int(text)
            time.sleep(0.05)
        self.fail(f"timed out waiting for non-empty pid in {path}")

    def test_start_script_exits_when_runtime_lock_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            runtime_dir = tmpdir_path / "runtime"
            holder_ready = tmpdir_path / "holder.ready"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)
            runtime_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh.write_text(START_SH.read_text(encoding="utf-8"), encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["TMUX"] = str(tmpdir_path / "tmux.sock")
            env["TMUX_PANE"] = "%0"
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            env["PSC_COST_REFRESH_DISABLED"] = "1"
            env["PSC_DREAM_DISABLED"] = "1"
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            env["FAKE_COCKPIT_MODE"] = "exit"
            env["FAKE_TMUX_LOG"] = str(tmpdir_path / "tmux.log")

            lock_path = runtime_dir / "paulshaclaw-start.lock"
            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import fcntl, os, sys, time; "
                        "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600); "
                        "fcntl.flock(fd, fcntl.LOCK_EX); "
                        "open(sys.argv[2], 'w', encoding='utf-8').write('ready'); "
                        "time.sleep(5)"
                    ),
                    str(lock_path),
                    str(holder_ready),
                ],
                env=env,
            )
            try:
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    if holder_ready.exists():
                        break
                    time.sleep(0.05)
                self.assertTrue(holder_ready.exists(), "lock holder never acquired the singleton lock")

                completed = subprocess.run(
                    ["bash", str(start_sh)],
                    cwd=repo_root,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            finally:
                holder.terminate()
                holder.wait(timeout=5)

            self.assertEqual(completed.returncode, 1)
            self.assertIn("已有實例在跑", completed.stdout)
            self.assertFalse(monitor_pidfile.exists())
            self.assertFalse(cockpit_pidfile.exists())
            self.assertFalse(cockpit_started.exists())

    def test_start_script_releases_singleton_lock_after_sigterm_with_active_dream_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            runtime_dir = tmpdir_path / "runtime"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"
            dream_pidfile = tmpdir_path / "dream.pid"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)
            runtime_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh.write_text(START_SH.read_text(encoding="utf-8"), encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["TMUX"] = str(tmpdir_path / "tmux.sock")
            env["TMUX_PANE"] = "%0"
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            env["PSC_COST_REFRESH_DISABLED"] = "1"
            memory_root = home_dir / ".agents" / "memory"
            memory_root.mkdir(parents=True, exist_ok=True)
            env["PSC_MEMORY_ROOT"] = str(memory_root)
            env["PSC_DREAM_INTERVAL_SECONDS"] = "1"
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            env["FAKE_DREAM_PIDFILE"] = str(dream_pidfile)
            env["FAKE_DREAM_MODE"] = "hold"
            env["FAKE_TMUX_LOG"] = str(tmpdir_path / "tmux.log")

            proc = subprocess.Popen(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                self._wait_for_pidfile_int(dream_pidfile, timeout=8.0)
                os.kill(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)

                second_env = dict(env)
                second_env["PSC_DREAM_DISABLED"] = "1"
                second_env["FAKE_COCKPIT_MODE"] = "exit"
                completed = subprocess.run(
                    ["bash", str(start_sh)],
                    cwd=repo_root,
                    env=second_env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                for pidfile in (monitor_pidfile, cockpit_pidfile, dream_pidfile):
                    if not pidfile.exists():
                        continue
                    try:
                        pid = int(pidfile.read_text(encoding="utf-8").strip())
                    except ValueError:
                        continue
                    with contextlib.suppress(ProcessLookupError):
                        os.kill(pid, signal.SIGKILL)

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


class StartScriptStage8FooterTests(unittest.TestCase):
    def test_fake_python_accepts_stage8_status_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            fake_python = tmpdir_path / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            completed = subprocess.run(
                [str(fake_python), "-m", "paulshaclaw.cost.status"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "cdx 5h:$12.34 wk:$56.78")
            self.assertEqual(completed.stderr, "")

    def test_start_script_applies_stage8_footer_inside_tmux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            tmux_log = tmpdir_path / "tmux.log"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh.write_text(
                START_SH.read_text(encoding="utf-8").replace(
                    "REPO=/home/paul_chen/prj_pri/paulshaclaw",
                    f"REPO={repo_root}",
                ),
                encoding="utf-8",
            )
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["TMUX"] = str(tmpdir_path / "tmux.sock")
            env["TMUX_PANE"] = "%0"
            runtime_dir = tmpdir_path / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            env["FAKE_COCKPIT_MODE"] = "exit"
            env["FAKE_TMUX_LOG"] = str(tmux_log)
            env["FAKE_TMUX_STATUS_RIGHT"] = "#[fg=green]existing"
            env["FAKE_TMUX_REFRESH_SECONDS"] = "45"

            completed = subprocess.run(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue(tmux_log.exists(), "tmux should be invoked inside tmux")
            calls = [json.loads(line) for line in tmux_log.read_text(encoding="utf-8").splitlines()]
            self.assertIn(["show-option", "-qv", "status-right"], calls)
            self.assertIn(["set-option", "status-interval", "45"], calls)
            self.assertIn(["set-option", "status-right-length", "200"], calls)
            self.assertNotIn(["set-option", "-g", "status-interval", "45"], calls)
            self.assertIn("cost refresh pid=", completed.stdout)

            status_right_calls = [call for call in calls if call[:2] == ["set-option", "status-right"]]
            self.assertEqual(len(status_right_calls), 1)
            status_right = status_right_calls[0][2]
            self.assertIn("#[fg=green]existing", status_right)
            self.assertIn("paulshaclaw.cost.status", status_right)
            self.assertIn("--no-refresh", status_right)
            self.assertNotIn("set-option -g", "\n".join(" ".join(call) for call in calls))
            self.assertFalse((home_dir / ".tmux.conf").exists())

    def test_start_script_passes_paulshaclaw_config_to_stage8_footer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            tmux_log = tmpdir_path / "tmux.log"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"
            config_path = tmpdir_path / "custom-paulshaclaw.yaml"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)
            config_path.write_text("workspaces: []\n", encoding="utf-8")

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh.write_text(
                START_SH.read_text(encoding="utf-8").replace(
                    "REPO=/home/paul_chen/prj_pri/paulshaclaw",
                    f"REPO={repo_root}",
                ),
                encoding="utf-8",
            )
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["TMUX"] = str(tmpdir_path / "tmux.sock")
            env["TMUX_PANE"] = "%0"
            runtime_dir = tmpdir_path / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            env["FAKE_COCKPIT_MODE"] = "exit"
            env["FAKE_TMUX_LOG"] = str(tmux_log)
            env["PAULSHACLAW_CONFIG"] = str(config_path)

            completed = subprocess.run(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            calls = [json.loads(line) for line in tmux_log.read_text(encoding="utf-8").splitlines()]
            status_right_calls = [call for call in calls if call[:2] == ["set-option", "status-right"]]
            self.assertEqual(len(status_right_calls), 1)
            status_right = status_right_calls[0][2]
            self.assertIn(f"PAULSHACLAW_CONFIG={config_path}", status_right)
            self.assertIn("paulshaclaw.cost.status", status_right)
            self.assertIn("--no-refresh", status_right)

    def test_start_script_falls_back_to_default_tmux_interval_when_config_load_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            tmux_log = tmpdir_path / "tmux.log"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh.write_text(
                START_SH.read_text(encoding="utf-8").replace(
                    "REPO=/home/paul_chen/prj_pri/paulshaclaw",
                    f"REPO={repo_root}",
                ),
                encoding="utf-8",
            )
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["TMUX"] = str(tmpdir_path / "tmux.sock")
            env["TMUX_PANE"] = "%0"
            runtime_dir = tmpdir_path / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            env["FAKE_COCKPIT_MODE"] = "exit"
            env["FAKE_TMUX_LOG"] = str(tmux_log)
            env["FAKE_TMUX_STATUS_RIGHT"] = ""
            env["FAKE_TMUX_REFRESH_ERROR"] = "1"

            completed = subprocess.run(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            calls = [json.loads(line) for line in tmux_log.read_text(encoding="utf-8").splitlines()]
            self.assertIn(["set-option", "status-interval", "30"], calls)


class StartScriptDreamLoopTests(unittest.TestCase):
    def test_dream_loop_sleeps_before_first_run(self) -> None:
        text = START_SH.read_text(encoding="utf-8")
        start = text.index("start_dream_loop() {")
        end = text.index("# Telegram listener", start)
        dream_block = text[start:end]

        sleep_index = dream_block.index('sleep "$interval"')
        run_index = dream_block.index('PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run')
        self.assertLess(sleep_index, run_index)

    def test_heavy_services_are_staggered_by_two_seconds(self) -> None:
        text = START_SH.read_text(encoding="utf-8")
        monitor_index = text.index('echo "monitor pid=$MONITOR_PID"')
        telegram_index = text.index('"$PY" -m paulshaclaw.bot.listener')
        cockpit_index = text.index('"$PY" -m paulshaclaw.cockpit')

        first_sleep = text.index("sleep 2", monitor_index)
        second_sleep = text.index("sleep 2", telegram_index)

        self.assertLess(monitor_index, first_sleep)
        self.assertLess(first_sleep, telegram_index)
        self.assertLess(telegram_index, second_sleep)
        self.assertLess(second_sleep, cockpit_index)
