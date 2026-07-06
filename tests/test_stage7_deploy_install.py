from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO = Path(__file__).resolve().parents[1]


def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
    path.chmod(0o755)


class DeployInstallTests(unittest.TestCase):
    def test_install_apply_is_idempotent_and_enables_linger_once(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            stubs = root / "stubs"
            logs = root / "logs"
            home.mkdir()
            stubs.mkdir()
            logs.mkdir()

            linger_file = logs / "linger.enabled"
            loginctl_log = logs / "loginctl.log"
            systemctl_log = logs / "systemctl.log"
            _write_stub(
                stubs / "loginctl",
                f"""
if [[ "${{1:-}}" == "show-user" ]]; then
  if [[ -f "{linger_file}" ]]; then
    printf 'yes\\n'
  else
    printf 'no\\n'
  fi
  exit 0
fi
printf '%s\\n' "$*" >> "{loginctl_log}"
if [[ "${{1:-}}" == "enable-linger" ]]; then
  : > "{linger_file}"
fi
""",
            )
            _write_stub(stubs / "systemctl", f'printf "%s\\n" "$*" >> "{systemctl_log}"\n')
            _write_stub(stubs / "systemd-analyze", 'echo "verify unavailable" >&2\nexit 127\n')

            env = {
                **os.environ,
                "HOME": str(home),
                "PATH": f"{stubs}:{os.environ['PATH']}",
                "PYTHONPATH": str(REPO),
                "USER": "demo",
            }
            cmd = [
                sys.executable,
                "-m",
                "paulshaclaw.deploy",
                "install",
                "--instance",
                "demo-agent",
                "--root-dir",
                "/srv/paulshaclaw",
                "--apply",
            ]
            first = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
            second = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)

            payload = json.loads(second.stdout)
            installed = {Path(p).name for p in payload["written_files"]}
            self.assertIn("demo-agent-dream.service", installed)
            self.assertIn("demo-agent-cost.service", installed)
            self.assertIn("demo-agent-manager.service", installed)
            self.assertIn("demo-agent-telegram.service", installed)
            self.assertIn("demo-agent-dream.env", installed)
            self.assertIn("demo-agent-cost.env", installed)
            self.assertIn("demo-agent-manager.env", installed)
            self.assertEqual(payload["linger_status"], "already-enabled")
            self.assertEqual(loginctl_log.read_text(encoding="utf-8").count("enable-linger demo"), 1)
            self.assertEqual(systemctl_log.read_text(encoding="utf-8").count("--user daemon-reload"), 2)

    def test_install_verify_fails_when_required_env_file_is_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            stubs = root / "stubs"
            home.mkdir()
            stubs.mkdir()

            _write_stub(stubs / "loginctl", 'printf "yes\\n"\n')
            _write_stub(stubs / "systemctl", "exit 0\n")
            _write_stub(stubs / "systemd-analyze", 'echo "verify unavailable" >&2\nexit 127\n')

            env = {
                **os.environ,
                "HOME": str(home),
                "PATH": f"{stubs}:{os.environ['PATH']}",
                "PYTHONPATH": str(REPO),
                "USER": "demo",
            }
            install_cmd = [
                sys.executable,
                "-m",
                "paulshaclaw.deploy",
                "install",
                "--instance",
                "demo-agent",
                "--root-dir",
                "/srv/paulshaclaw",
                "--apply",
            ]
            installed = subprocess.run(install_cmd, check=False, capture_output=True, text=True, env=env)
            self.assertEqual(installed.returncode, 0, installed.stderr)

            missing_env = home / ".agents" / "core" / "runtime" / "demo-agent-dream.env"
            missing_env.unlink()

            verify_cmd = [
                sys.executable,
                "-m",
                "paulshaclaw.deploy",
                "install",
                "--instance",
                "demo-agent",
                "--root-dir",
                "/srv/paulshaclaw",
                "--verify",
            ]
            verified = subprocess.run(verify_cmd, check=False, capture_output=True, text=True, env=env)
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("demo-agent-dream.env", verified.stderr)
            self.assertNotIn("PSC_TELEGRAM_BOT_TOKEN=", verified.stderr)


if __name__ == "__main__":
    unittest.main()
