from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
START_SH = REPO / "scripts" / "start.sh"

# 抽出 start_manager_service 函式單獨跑（避免 source 整支 start.sh 的副作用）
_HARNESS = """
set -euo pipefail
fn="$(sed -n '/^start_manager_service()/,/^}}/p' "{start_sh}")"
eval "$fn"
start_manager_service
"""


def _run(stub_dir: Path, env: dict) -> subprocess.CompletedProcess:
    script = _HARNESS.format(start_sh=str(START_SH))
    full_env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}", **env}
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=full_env)


def _write_stub(d: Path, name: str, body: str) -> None:
    p = d / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    p.chmod(0o755)


class StartManagerServiceTests(unittest.TestCase):
    def test_disabled_skips(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            _write_stub(sd, "systemctl", 'echo "SYSTEMCTL $*" >> "' + str(sd / "systemctl.log") + '"\nexit 0\n')
            res = _run(sd, {"PSC_MANAGER_DISABLED": "1", "PSC_INSTANCE": "demo"})
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("disabled", res.stdout)
            self.assertFalse((sd / "systemctl.log").exists())

    def test_no_user_systemd_graceful_skip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            # systemctl 存在但 `--user show-environment` 失敗 → 模擬 WSL 無 user systemd
            _write_stub(sd, "systemctl", 'if [[ "$1 $2" == "--user show-environment" ]]; then exit 1; fi\nexit 0\n')
            res = _run(sd, {"PSC_INSTANCE": "demo"})
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("skipped", res.stderr + res.stdout)

    def test_starts_timer(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            log = sd / "calls.log"
            _write_stub(sd, "systemctl", f'echo "$*" >> "{log}"\nexit 0\n')
            res = _run(sd, {"PSC_INSTANCE": "demo"})
            self.assertEqual(res.returncode, 0, res.stderr)
            calls = log.read_text(encoding="utf-8") if log.exists() else ""
            self.assertIn("--user start demo-manager.timer", calls)


if __name__ == "__main__":
    unittest.main()
