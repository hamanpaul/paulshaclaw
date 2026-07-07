from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def make_test_dir(name: str) -> Path:
    path = REPO_ROOT / ".test-artifacts" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_script(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_fake_tools(base: Path, *, include_systemd_analyze: bool) -> tuple[Path, Path]:
    fakebin = base / "fakebin"
    fakebin.mkdir(parents=True, exist_ok=True)
    command_log = base / "command.log"
    linger_flag = base / "linger.enabled"

    write_script(
        fakebin / "systemctl",
        f"""#!/bin/bash
set -euo pipefail
printf '%s\\n' "systemctl $*" >> "{command_log}"
exit 0
""",
    )
    write_script(
        fakebin / "loginctl",
        f"""#!/bin/bash
set -euo pipefail
printf '%s\\n' "loginctl $*" >> "{command_log}"
if [[ "${{1:-}}" == "show-user" ]]; then
  if [[ -f "{linger_flag}" ]]; then
    printf 'yes\\n'
  else
    printf 'no\\n'
  fi
  exit 0
fi
if [[ "${{1:-}}" == "enable-linger" ]]; then
  : > "{linger_flag}"
  exit 0
fi
exit 0
""",
    )
    if include_systemd_analyze:
        write_script(
            fakebin / "systemd-analyze",
            f"""#!/bin/bash
set -euo pipefail
printf '%s\\n' "systemd-analyze $*" >> "{command_log}"
exit 0
""",
        )
    return fakebin, command_log


def deploy_env(home_dir: Path, fakebin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home_dir),
            "PATH": str(fakebin),
            "USER": "stage7tester",
            "LOGNAME": "stage7tester",
        }
    )
    return env


def run_deploy_install(home_dir: Path, fakebin: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "paulshaclaw.deploy",
            "install",
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
            *args,
        ],
        cwd=REPO_ROOT,
        env=deploy_env(home_dir, fakebin),
        check=False,
        capture_output=True,
        text=True,
    )


class DeployInstallCliTests(unittest.TestCase):
    def test_install_apply_renders_units_runtime_state_and_secret_files_idempotently(self) -> None:
        scratch = make_test_dir("stage7-install-apply")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, command_log = make_fake_tools(scratch, include_systemd_analyze=True)
        try:
            first = run_deploy_install(home_dir, fakebin, "--apply", "--verify")
            second = run_deploy_install(home_dir, fakebin, "--apply", "--verify")

            self.assertEqual(first.returncode, 0, msg=first.stderr)
            self.assertEqual(second.returncode, 0, msg=second.stderr)

            payload = json.loads(second.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["verification"]["status"], "passed")
            self.assertEqual(payload["verification"]["systemd"]["status"], "passed")

            unit_dir = home_dir / ".config" / "systemd" / "user"
            runtime_dir = home_dir / ".agents" / "core" / "runtime"
            state_dir = home_dir / ".agents" / "state" / "config"
            secret_dir = home_dir / ".config" / "paulshaclaw"

            for relpath in (
                unit_dir / "demo-agent-dream.service",
                unit_dir / "demo-agent-cost.service",
                unit_dir / "demo-agent-manager.service",
                unit_dir / "demo-agent-telegram.service",
                runtime_dir / "demo-agent.env",
                runtime_dir / "demo-agent-dream.env",
                runtime_dir / "demo-agent-cost.env",
                runtime_dir / "demo-agent-manager.env",
                runtime_dir / "demo-agent-telegram.env",
                state_dir / "demo-agent.state.json",
                secret_dir / "demo-agent.secret.env",
                secret_dir / "demo-agent.telegram.secret.env",
            ):
                self.assertTrue(relpath.exists(), msg=str(relpath))

            self.assertFalse((unit_dir / "demo-agent-manager.timer").exists())
            self.assertEqual(stat.S_IMODE(state_dir.stat().st_mode), 0o750)
            self.assertEqual(stat.S_IMODE(secret_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((state_dir / "demo-agent.state.json").stat().st_mode), 0o640)
            self.assertEqual(stat.S_IMODE((secret_dir / "demo-agent.secret.env").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((secret_dir / "demo-agent.telegram.secret.env").stat().st_mode), 0o600)
            state_payload = json.loads((state_dir / "demo-agent.state.json").read_text(encoding="utf-8"))
            self.assertEqual(state_payload["default_project"], "demo-agent")
            self.assertIn("daemon_name", state_payload)
            self.assertEqual(state_payload["coordinator"]["phase"], "build")
            self.assertIn("pane_assignments", state_payload)

            dream_unit = (unit_dir / "demo-agent-dream.service").read_text(encoding="utf-8")
            manager_unit = (unit_dir / "demo-agent-manager.service").read_text(encoding="utf-8")
            telegram_unit = (unit_dir / "demo-agent-telegram.service").read_text(encoding="utf-8")
            for text, script_name in (
                (dream_unit, "service-dream.sh"),
                (manager_unit, "service-manager.sh"),
                (telegram_unit, "service-bot.sh"),
            ):
                self.assertIn("Restart=on-failure", text)
                self.assertIn("RestartSec=10", text)
                self.assertIn("StartLimitIntervalSec=300", text)
                self.assertIn("StartLimitBurst=5", text)
                self.assertIn("KillMode=control-group", text)
                self.assertIn(f"ExecStart=/usr/bin/env bash /srv/paulshaclaw/scripts/{script_name}", text)
                self.assertNotIn("/home/", text)

            log_text = command_log.read_text(encoding="utf-8")
            self.assertEqual(log_text.count("loginctl enable-linger stage7tester"), 1)
            self.assertGreaterEqual(log_text.count("systemctl --user daemon-reload"), 2)
            self.assertGreaterEqual(log_text.count("systemd-analyze --user verify"), 2)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_verify_reports_missing_file_and_key_without_printing_values(self) -> None:
        scratch = make_test_dir("stage7-install-verify-fail")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _command_log = make_fake_tools(scratch, include_systemd_analyze=True)
        try:
            applied = run_deploy_install(home_dir, fakebin, "--apply")
            self.assertEqual(applied.returncode, 0, msg=applied.stderr)

            runtime_dir = home_dir / ".agents" / "core" / "runtime"
            dream_env = runtime_dir / "demo-agent-dream.env"
            dream_env.write_text(
                "\n".join(
                    line
                    for line in dream_env.read_text(encoding="utf-8").splitlines()
                    if not line.startswith("PSC_DREAM_INTERVAL_SECONDS=")
                )
                + "\n",
                encoding="utf-8",
            )
            (runtime_dir / "demo-agent-cost.env").unlink()

            secret_file = home_dir / ".config" / "paulshaclaw" / "demo-agent.telegram.secret.env"
            secret_file.write_text(
                "PSC_TELEGRAM_BOT_TOKEN=top-secret-token\nPSC_TELEGRAM_EXPECTED_USERNAME=\nPSC_TELEGRAM_EXPECTED_BOT_ID=\nPSC_CLAUDE_GEMMA4_API_KEY=\n",
                encoding="utf-8",
            )

            verified = run_deploy_install(home_dir, fakebin, "--verify")

            self.assertEqual(verified.returncode, 1, msg=verified.stdout)
            combined = verified.stdout + verified.stderr
            self.assertIn("demo-agent-cost.env", combined)
            self.assertIn("demo-agent-dream.env", combined)
            self.assertIn("PSC_DREAM_INTERVAL_SECONDS", combined)
            self.assertNotIn("top-secret-token", combined)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_verify_fails_when_expected_unit_is_missing(self) -> None:
        scratch = make_test_dir("stage7-install-verify-missing-unit")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _command_log = make_fake_tools(scratch, include_systemd_analyze=True)
        try:
            applied = run_deploy_install(home_dir, fakebin, "--apply")
            self.assertEqual(applied.returncode, 0, msg=applied.stderr)

            missing_unit = home_dir / ".config" / "systemd" / "user" / "demo-agent-manager.service"
            missing_unit.unlink()

            verified = run_deploy_install(home_dir, fakebin, "--verify")

            self.assertEqual(verified.returncode, 1, msg=verified.stdout)
            combined = verified.stdout + verified.stderr
            self.assertIn("demo-agent-manager.service", combined)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_verify_fails_when_stage1_config_is_invalid(self) -> None:
        scratch = make_test_dir("stage7-install-verify-bad-stage1-config")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _command_log = make_fake_tools(scratch, include_systemd_analyze=True)
        try:
            applied = run_deploy_install(home_dir, fakebin, "--apply")
            self.assertEqual(applied.returncode, 0, msg=applied.stderr)

            state_config = home_dir / ".agents" / "state" / "config" / "demo-agent.state.json"
            state_payload = json.loads(state_config.read_text(encoding="utf-8"))
            state_payload.pop("daemon_name", None)
            state_config.write_text(json.dumps(state_payload), encoding="utf-8")

            verified = run_deploy_install(home_dir, fakebin, "--verify")

            self.assertEqual(verified.returncode, 1, msg=verified.stdout)
            combined = verified.stdout + verified.stderr
            self.assertIn("demo-agent.state.json", combined)
            self.assertIn("config.daemon_name", combined)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_install_verify_degrades_to_on_host_only_when_systemd_analyze_is_unavailable(self) -> None:
        scratch = make_test_dir("stage7-install-verify-degrade")
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        fakebin, _command_log = make_fake_tools(scratch, include_systemd_analyze=False)
        try:
            applied = run_deploy_install(home_dir, fakebin, "--apply")
            self.assertEqual(applied.returncode, 0, msg=applied.stderr)

            verified = run_deploy_install(home_dir, fakebin, "--verify")

            self.assertEqual(verified.returncode, 0, msg=verified.stderr)
            payload = json.loads(verified.stdout)
            self.assertEqual(payload["verification"]["status"], "passed")
            self.assertEqual(payload["verification"]["systemd"]["status"], "on-host-only")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class ApplyInstallPlanCreateOnlyTests(unittest.TestCase):
    """#219 對抗審查 F1：rerun 不得以 placeholder 覆寫使用者持有檔。"""

    def test_rerun_preserves_state_secret_and_runtime_env_but_updates_units(self) -> None:
        from paulshaclaw.deploy.installer import apply_install_plan
        from paulshaclaw.deploy.planner import build_command_plan

        scratch = make_test_dir("stage7-install-create-only")
        if True:
            home_dir = scratch / "home"
            home_dir.mkdir(parents=True, exist_ok=True)
            plan = build_command_plan("install", instance_name="demo-agent", root_dir="/srv/paulshaclaw")

            first = apply_install_plan(plan, home_dir=home_dir)
            self.assertEqual(first["skipped_existing"], [])

            secret_path = home_dir / ".config" / "paulshaclaw" / "demo-agent.telegram.secret.env"
            state_path = home_dir / ".agents" / "state" / "config" / "demo-agent.state.json"
            env_path = home_dir / ".agents" / "core" / "runtime" / "demo-agent-dream.env"
            unit_path = home_dir / ".config" / "systemd" / "user" / "demo-agent-dream.service"
            for p in (secret_path, state_path, env_path, unit_path):
                self.assertTrue(p.is_file(), p)

            secret_path.write_text("PSC_TELEGRAM_BOT_TOKEN=real-operator-token\n", encoding="utf-8")
            state_path.write_text('{"allowed_user_ids": [42]}\n', encoding="utf-8")
            env_path.write_text("PSC_DREAM_INTERVAL_SECONDS=7200\n", encoding="utf-8")
            unit_path.write_text("[Unit]\nDescription=stale unit to be upgraded\n", encoding="utf-8")

            second = apply_install_plan(plan, home_dir=home_dir)

            self.assertIn("real-operator-token", secret_path.read_text(encoding="utf-8"))
            self.assertIn("[42]", state_path.read_text(encoding="utf-8"))
            self.assertIn("7200", env_path.read_text(encoding="utf-8"))
            self.assertNotIn("stale unit", unit_path.read_text(encoding="utf-8"))  # unit 檔允許覆寫
            self.assertIn(str(secret_path), second["skipped_existing"])
            self.assertIn(str(state_path), second["skipped_existing"])
            self.assertIn(str(env_path), second["skipped_existing"])
            self.assertIn(str(unit_path), second["written"])
