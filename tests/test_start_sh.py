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
            signal.pause()
            return 0

        if module == "paulshaclaw.cockpit":
            Path(os.environ["FAKE_COCKPIT_STARTED"]).write_text("started", encoding="utf-8")
            signal.pause()
            return 0

        print(f"unexpected argv: {sys.argv!r}", file=sys.stderr)
        return 2


    if __name__ == "__main__":
        raise SystemExit(main())
    """
)


class StartScriptLifecycleTests(unittest.TestCase):
    def test_monitor_is_terminated_when_cockpit_receives_sigint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            telegram_pidfile = tmpdir_path / "telegram.pid"
            cockpit_started = tmpdir_path / "cockpit.started"

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
            start_sh.write_text(start_sh_text, encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["TMUX_PANE"] = "%0"
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_TELEGRAM_PIDFILE"] = str(telegram_pidfile)
            env["FAKE_COCKPIT_STARTED"] = str(cockpit_started)

            proc = subprocess.Popen(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                self._wait_for_file(monitor_pidfile)
                self._wait_for_file(telegram_pidfile)
                self._wait_for_file(cockpit_started)
                monitor_pid = int(monitor_pidfile.read_text(encoding="utf-8").strip())
                telegram_pid = int(telegram_pidfile.read_text(encoding="utf-8").strip())

                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                proc.wait(timeout=10)

                with self.assertRaises(ProcessLookupError):
                    os.kill(monitor_pid, 0)
                with self.assertRaises(ProcessLookupError):
                    os.kill(telegram_pid, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                if monitor_pidfile.exists():
                    try:
                        os.kill(int(monitor_pidfile.read_text(encoding="utf-8").strip()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if telegram_pidfile.exists():
                    try:
                        os.kill(int(telegram_pidfile.read_text(encoding="utf-8").strip()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def _wait_for_file(self, path: Path, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(0.05)
        self.fail(f"timed out waiting for {path}")
