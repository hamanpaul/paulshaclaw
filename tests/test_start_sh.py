from __future__ import annotations

import json
import os
import signal
import subprocess
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

    def test_monitor_immediate_exit_prevents_cockpit_start(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_mode="ready",
            monitor_mode="exit",
            expect_cockpit_started=False,
            expect_returncode=1,
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

            start_sh = fake_scripts / "start.sh"
            start_sh_text = START_SH.read_text(encoding="utf-8").replace(
                "REPO=/home/paul_chen/prj_pri/paulshaclaw",
                f"REPO={repo_root}",
            )
            self.assertNotIn("set -m", start_sh_text)
            self.assertNotIn("while kill -0", start_sh_text)
            start_sh.write_text(start_sh_text, encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["TMUX_PANE"] = "%0"
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

    def _wait_for_pidfile_int(self, path: Path, timeout: float = 5.0) -> int:
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
            self.assertNotIn(["set-option", "-g", "status-interval", "45"], calls)

            status_right_calls = [call for call in calls if call[:2] == ["set-option", "status-right"]]
            self.assertEqual(len(status_right_calls), 1)
            status_right = status_right_calls[0][2]
            self.assertIn("#[fg=green]existing", status_right)
            self.assertIn("paulshaclaw.cost.status", status_right)
            self.assertNotIn("set-option -g", "\n".join(" ".join(call) for call in calls))
            self.assertFalse((home_dir / ".tmux.conf").exists())

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
