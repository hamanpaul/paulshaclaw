from __future__ import annotations

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
        if module == "paulshaclaw.monitor":
            pidfile = Path(os.environ["FAKE_MONITOR_PIDFILE"])
            pidfile.write_text(str(os.getpid()), encoding="utf-8")
            signal.signal(signal.SIGINT, signal.SIG_IGN)
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
            readyfile = Path(os.environ["FAKE_TELEGRAM_READYFILE"])
            time.sleep(0.2)
            readyfile.write_text("ready", encoding="utf-8")
            print("Telegram listener ready", flush=True)
            signal.pause()
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


class StartScriptLifecycleTests(unittest.TestCase):
    def test_monitor_and_cockpit_start_without_telegram_inputs(self) -> None:
        self._run_lifecycle_test(cockpit_mode="exit", telegram_enabled=False, capture_output=True)

    def test_monitor_cockpit_and_telegram_ready_when_inputs_present(self) -> None:
        self._run_lifecycle_test(signal_to_wrapper=signal.SIGTERM, telegram_enabled=True, telegram_mode="ready")

    def test_telegram_init_failure_prevents_success(self) -> None:
        self._run_lifecycle_test(
            telegram_enabled=True,
            telegram_mode="init-fail",
            expect_cockpit_started=False,
            expect_returncode=1,
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
        telegram_mode: str = "ready",
        expect_cockpit_started: bool = True,
        expect_returncode: int | None = None,
        capture_output: bool = False,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            telegram_pidfile = tmpdir_path / "telegram.pid"
            telegram_readyfile = tmpdir_path / "telegram.ready"
            cockpit_pidfile = tmpdir_path / "cockpit.pid"
            cockpit_started = tmpdir_path / "cockpit.started"
            stage1_config = tmpdir_path / "stage1.json"
            telegram_log = home_dir / ".agents" / "log" / "telegram.log"

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
            env["FAKE_COCKPIT_PIDFILE"] = str(cockpit_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)
            if telegram_enabled:
                stage1_config.write_text("{}", encoding="utf-8")
                env["PSC_TELEGRAM_BOT_TOKEN"] = "fake-token"
                env["PSC_STAGE1_CONFIG"] = str(stage1_config)
                env["FAKE_TELEGRAM_PIDFILE"] = str(telegram_pidfile)
                env["FAKE_TELEGRAM_READYFILE"] = str(telegram_readyfile)
                env["FAKE_TELEGRAM_MODE"] = telegram_mode
            if cockpit_mode is not None:
                env["FAKE_COCKPIT_MODE"] = cockpit_mode

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
                monitor_pid = self._wait_for_pidfile_int(monitor_pidfile)
                if expect_cockpit_started:
                    cockpit_pid = self._wait_for_pidfile_int(cockpit_pidfile)
                    self._wait_for_file(cockpit_started)
                else:
                    self._wait_for_missing_file(cockpit_started)
                if telegram_enabled:
                    telegram_pid = self._wait_for_pidfile_int(telegram_pidfile)
                    if telegram_mode == "ready":
                        self._wait_for_log_line(telegram_log, "Telegram listener ready")
                        self._wait_for_file(telegram_readyfile)
                        self.assertLessEqual(
                            telegram_readyfile.stat().st_mtime_ns,
                            cockpit_started.stat().st_mtime_ns,
                        )
                    else:
                        self._wait_for_missing_file(telegram_readyfile)
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

                with self.assertRaises(ProcessLookupError):
                    os.kill(monitor_pid, 0)
                if telegram_enabled:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(telegram_pid, 0)
                if expect_cockpit_started:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(cockpit_pid, 0)

                if capture_output:
                    output = proc.communicate(timeout=10)[0]
                    self.assertIn("telegram skipped", output)
                    self.assertNotIn("telegram pid=", output)
                    if telegram_enabled and telegram_mode == "init-fail":
                        self.assertNotIn("Telegram listener ready", output)
                        self.assertIn("telegram listener exited before ready", output)

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

    def _wait_for_log_line(self, path: Path, needle: str, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and needle in path.read_text(encoding="utf-8"):
                return
            time.sleep(0.05)
        self.fail(f"timed out waiting for {needle!r} in {path}")
