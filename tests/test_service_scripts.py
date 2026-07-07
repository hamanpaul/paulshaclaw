from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


class ServiceScriptTests(unittest.TestCase):
    def test_service_scripts_exist(self) -> None:
        for path in self._service_scripts().values():
            self.assertTrue(path.exists(), f"missing service script: {path.name}")

    def test_service_scripts_have_valid_bash_syntax(self) -> None:
        for name, path in self._service_scripts().items():
            with self.subTest(script=name):
                completed = subprocess.run(
                    ["bash", "-n", str(path)],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{path.name} failed bash -n:\nstdout={completed.stdout}\nstderr={completed.stderr}",
                )

    def test_service_scripts_use_bash_shebang(self) -> None:
        for name, path in self._service_scripts().items():
            with self.subTest(script=name):
                self.assertEqual(
                    path.read_text(encoding="utf-8").splitlines()[0],
                    "#!/usr/bin/env bash",
                    f"{path.name} must start with a bash shebang",
                )

    def test_service_scripts_are_executable(self) -> None:
        for name, path in self._service_scripts().items():
            with self.subTest(script=name):
                self.assertTrue(
                    path.stat().st_mode & stat.S_IXUSR,
                    f"{path.name} must keep the user executable bit",
                )

    def test_cost_service_runs_cost_once_with_repo_pythonpath(self) -> None:
        text = self._read("cost")
        self.assertIn('PYTHONPATH="$REPO" "$PY" -m paulshaclaw.cost --once', text)

    def test_dream_service_runs_memory_dream_command(self) -> None:
        text = self._read("dream")
        self.assertIn('PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run', text)
        self.assertIn('--memory-root "$dream_root"', text)
        self.assertIn("--require-idle", text)
        self.assertIn("--promoter llm", text)

    def test_manager_service_runs_daemon_with_repo_specs_dir(self) -> None:
        text = self._read("manager")
        self.assertIn('PYTHONPATH="$REPO" "$PY" -m paulshaclaw.coordinator.manager_daemon', text)
        self.assertIn('--specs-dir "$REPO/docs/superpowers/specs"', text)
        self.assertIn("manager_startup_checks", text)
        self.assertNotIn("SECONDS", text)

    def test_bot_service_launches_listener_with_readiness_guard(self) -> None:
        text = self._read("bot")
        self.assertIn('PYTHONPATH="$REPO" "$PY" -m paulshaclaw.bot.listener', text)
        self.assertIn('export PSC_TELEGRAM_READY_FILE="$TELEGRAM_READY_FILE"', text)
        self.assertIn("telegram listener readiness timeout", text)

    def _service_scripts(self) -> dict[str, Path]:
        return {
            "bot": SCRIPTS_DIR / "service-bot.sh",
            "cost": SCRIPTS_DIR / "service-cost.sh",
            "dream": SCRIPTS_DIR / "service-dream.sh",
            "manager": SCRIPTS_DIR / "service-manager.sh",
        }

    def _read(self, name: str) -> str:
        return self._service_scripts()[name].read_text(encoding="utf-8")


class CostServiceSystemdBehaviorTests(unittest.TestCase):
    """#219 對抗審查 F2：systemd 直跑（無 TMUX）不得靜默 exit 0 不動。"""

    def test_cost_service_runs_without_tmux_reaches_loop_logic(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "service-cost.sh"
        env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PSC_COST_REFRESH_DISABLED": "1"}
        completed = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            env=env,  # 無 TMUX——模擬 systemd 環境
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        # guard 移除後必須抵達 loop 邏輯（此處由 disabled 訊息證明），
        # 而非在 TMUX 檢查就 return 0 靜默結束。
        self.assertIn("cost refresh loop disabled", completed.stdout)



if __name__ == "__main__":
    unittest.main()
