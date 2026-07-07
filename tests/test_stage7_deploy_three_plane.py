from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from paulshaclaw.deploy import (
    build_command_plan,
    complete_secret_install_flow,
    list_template_assets,
    resolve_template_target,
    validate_plane_permissions,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_test_dir(name: str) -> Path:
    path = REPO_ROOT / ".test-artifacts" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


class TemplateMappingTests(unittest.TestCase):
    def test_template_assets_cover_three_planes(self) -> None:
        assets = list_template_assets()
        relpaths = {asset.template_relpath for asset in assets}
        planes = {asset.plane for asset in assets}

        self.assertGreaterEqual(len(assets), 13)
        self.assertTrue({"core", "state", "secret"}.issubset(planes))
        self.assertTrue(
            {
                "core/systemd/__INSTANCE__.service.tmpl",
                "core/systemd/__INSTANCE__-dream.service.tmpl",
                "core/systemd/__INSTANCE__-cost.service.tmpl",
                "core/systemd/__INSTANCE__-manager.service.tmpl",
                "core/systemd/__INSTANCE__-manager.timer.tmpl",
                "core/systemd/__INSTANCE__-telegram.service.tmpl",
                "core/runtime/__INSTANCE__.env.tmpl",
                "core/runtime/__INSTANCE__-dream.env.tmpl",
                "core/runtime/__INSTANCE__-cost.env.tmpl",
                "core/runtime/__INSTANCE__-manager.env.tmpl",
                "core/runtime/__INSTANCE__-telegram.env.tmpl",
                "state/config/__INSTANCE__.state.json.tmpl",
                "secret/bootstrap/__INSTANCE__.secret.env.tmpl",
                "secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl",
            }.issubset(relpaths)
        )
        for asset in assets:
            self.assertTrue(asset.template_path.exists(), msg=str(asset.template_path))
            self.assertTrue(asset.target_path.endswith(asset.expected_suffix))

        telegram_unit = next(
            asset for asset in assets if asset.template_relpath == "core/systemd/__INSTANCE__-telegram.service.tmpl"
        )
        telegram_unit_text = telegram_unit.template_path.read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__.env", telegram_unit_text)
        self.assertIn("EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__-telegram.env", telegram_unit_text)
        self.assertIn("EnvironmentFile=%h/.config/paulshaclaw/__INSTANCE__.telegram.secret.env", telegram_unit_text)
        self.assertIn("ExecStart=/usr/bin/env bash __ROOT_DIR__/scripts/service-bot.sh", telegram_unit_text)
        self.assertIn("Environment=PSC_STAGE1_CONFIG=%h/.agents/state/config/__INSTANCE__.state.json", telegram_unit_text)
        self.assertEqual(
            telegram_unit.env_catalog,
            (
                "core/runtime/__INSTANCE__.env",
                "core/runtime/__INSTANCE__-telegram.env",
                "secret/bootstrap/__INSTANCE__.telegram.secret.env",
            ),
        )

        telegram_runtime = next(
            asset for asset in assets if asset.template_relpath == "core/runtime/__INSTANCE__-telegram.env.tmpl"
        )
        telegram_runtime_text = telegram_runtime.template_path.read_text(encoding="utf-8")
        self.assertIn("PSC_INSTANCE=__INSTANCE__", telegram_runtime_text)
        self.assertIn("PSC_PLANE=core", telegram_runtime_text)
        self.assertNotIn("PSC_STAGE1_CONFIG", telegram_runtime_text)

        core_unit = next(asset for asset in assets if asset.template_relpath == "core/systemd/__INSTANCE__.service.tmpl")
        core_unit_text = core_unit.template_path.read_text(encoding="utf-8")
        self.assertIn("WantedBy=default.target", core_unit_text)

        telegram_secret = next(
            asset for asset in assets if asset.template_relpath == "secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl"
        )
        telegram_secret_text = telegram_secret.template_path.read_text(encoding="utf-8")
        self.assertIn("PSC_TELEGRAM_BOT_TOKEN=", telegram_secret_text)
        self.assertIn("PSC_TELEGRAM_EXPECTED_USERNAME=", telegram_secret_text)
        self.assertIn("PSC_TELEGRAM_EXPECTED_BOT_ID=", telegram_secret_text)
        self.assertIn("PSC_CLAUDE_GEMMA4_API_KEY=", telegram_secret_text)
        self.assertNotIn("OPENAI_BASE_URL", telegram_secret_text)
        self.assertNotIn("OPENAI_API_KEY", telegram_secret_text)
        self.assertNotIn("OPENAI_MODEL", telegram_secret_text)
        self.assertNotIn("OPENAI_TIMEOUT_SECONDS", telegram_secret_text)

    def test_rename_rule_strips_tmpl_and_replaces_instance_token(self) -> None:
        target = resolve_template_target(
            "core/systemd/__INSTANCE__.service.tmpl",
            instance_name="demo-agent",
        )

        self.assertEqual(target, "core/systemd/demo-agent.service")
        self.assertEqual(
            resolve_template_target("core/systemd/__INSTANCE__-telegram.service.tmpl", instance_name="demo-agent"),
            "core/systemd/demo-agent-telegram.service",
        )
        self.assertEqual(
            resolve_template_target("core/runtime/__INSTANCE__-telegram.env.tmpl", instance_name="demo-agent"),
            "core/runtime/demo-agent-telegram.env",
        )
        self.assertEqual(
            resolve_template_target("secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl", instance_name="demo-agent"),
            "secret/bootstrap/demo-agent.telegram.secret.env",
        )


class PermissionPolicyTests(unittest.TestCase):
    def test_state_plane_rejects_world_writable_mode(self) -> None:
        result = validate_plane_permissions("state", 0o777)

        self.assertFalse(result.allowed)
        self.assertIn("state", result.reason)

    def test_secret_plane_rejects_group_readable_mode(self) -> None:
        result = validate_plane_permissions("secret", 0o750)

        self.assertFalse(result.allowed)
        self.assertIn("secret", result.reason)

    def test_safe_modes_are_accepted(self) -> None:
        self.assertTrue(validate_plane_permissions("state", 0o750).allowed)
        self.assertTrue(validate_plane_permissions("secret", 0o700).allowed)


class SecretInstallFlowTests(unittest.TestCase):
    def test_secret_install_flow_requires_permission_ack(self) -> None:
        with self.assertRaisesRegex(ValueError, "0700/0600"):
            complete_secret_install_flow(
                {
                    "secret_source": "git@internal.example:secrets/stage7.git",
                    "secret_target": "/srv/paulshaclaw/secret",
                    "permission_ack": "no",
                }
            )

    def test_secret_install_flow_returns_checkpointed_summary(self) -> None:
        summary = complete_secret_install_flow(
            {
                "secret_source": "git@internal.example:secrets/stage7.git",
                "secret_target": "/srv/paulshaclaw/secret",
                "permission_ack": "yes",
            }
        )

        self.assertEqual(summary["plane"], "secret")
        self.assertEqual(summary["source_kind"], "private-repo")
        self.assertIn("secret-preflight", summary["checkpoints"])
        self.assertIn("secret-installed", summary["checkpoints"])


class CommandPlanTests(unittest.TestCase):
    def test_install_upgrade_uninstall_plans_have_expected_restore_policy(self) -> None:
        for command in ("install", "upgrade", "uninstall"):
            with self.subTest(command=command):
                plan = build_command_plan(
                    command=command,
                    instance_name="demo-agent",
                    root_dir="/srv/paulshaclaw",
                )
                self.assertEqual(plan.command, command)
                self.assertGreaterEqual(len(plan.rollback_checkpoints), 1)
                self.assertGreaterEqual(len(plan.rollback_actions), 1)

        upgrade = build_command_plan("upgrade", instance_name="demo-agent", root_dir="/srv/paulshaclaw")
        self.assertIn("preserve-state", upgrade.rollback_actions)
        self.assertIn("preserve-secret", upgrade.rollback_actions)

        uninstall = build_command_plan("uninstall", instance_name="demo-agent", root_dir="/srv/paulshaclaw")
        self.assertIn("preserve-state", uninstall.rollback_actions)
        self.assertIn("preserve-secret", uninstall.rollback_actions)

    def test_install_plan_excludes_deprecated_timer_and_wires_service_verify_targets(self) -> None:
        plan = build_command_plan("install", instance_name="demo-agent", root_dir="/srv/paulshaclaw")
        relpaths = {asset.template_relpath for asset in plan.templates}

        self.assertIn("core/systemd/__INSTANCE__-dream.service.tmpl", relpaths)
        self.assertIn("core/systemd/__INSTANCE__-cost.service.tmpl", relpaths)
        self.assertIn("core/runtime/__INSTANCE__-dream.env.tmpl", relpaths)
        self.assertIn("core/runtime/__INSTANCE__-cost.env.tmpl", relpaths)
        self.assertNotIn("core/systemd/__INSTANCE__-manager.timer.tmpl", relpaths)
        self.assertIn("verify-systemd-user-units", plan.steps)
        self.assertEqual(
            set(plan.verify_units),
            {
                "demo-agent.service",
                "demo-agent-dream.service",
                "demo-agent-cost.service",
                "demo-agent-manager.service",
                "demo-agent-telegram.service",
            },
        )


class DeployCliTests(unittest.TestCase):
    def test_cli_subcommands_emit_json_plan(self) -> None:
        tmpdir = make_test_dir("stage7-deploy-cli")
        try:
            for command in ("install", "upgrade", "uninstall"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "paulshaclaw.deploy",
                        command,
                        "--instance",
                        "demo-agent",
                        "--root-dir",
                        str(tmpdir),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["command"], command)
                self.assertEqual(payload["instance_name"], "demo-agent")
                self.assertTrue(payload["templates"])
                self.assertTrue(payload["rollback_checkpoints"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class ManagerUnitCatalogTests(unittest.TestCase):
    def test_manager_units_present_and_rename(self) -> None:
        assets = list_template_assets()
        relpaths = {a.template_relpath for a in assets}
        for rp in (
            "core/systemd/__INSTANCE__-manager.service.tmpl",
            "core/systemd/__INSTANCE__-manager.timer.tmpl",
            "core/runtime/__INSTANCE__-manager.env.tmpl",
        ):
            self.assertIn(rp, relpaths)

        svc = next(a for a in assets if a.template_relpath == "core/systemd/__INSTANCE__-manager.service.tmpl")
        svc_text = svc.template_path.read_text(encoding="utf-8")
        self.assertTrue(svc.deploy)
        self.assertEqual(svc.env_catalog, ("core/runtime/__INSTANCE__.env", "core/runtime/__INSTANCE__-manager.env"))
        self.assertIn("Restart=on-failure", svc_text)
        self.assertIn("RestartSec=10", svc_text)
        self.assertIn("StartLimitIntervalSec=300", svc_text)
        self.assertIn("StartLimitBurst=5", svc_text)
        self.assertIn("KillMode=control-group", svc_text)
        self.assertIn("ExecStart=/usr/bin/env bash __ROOT_DIR__/scripts/service-manager.sh", svc_text)
        self.assertNotIn("/home/", svc_text)
        self.assertNotIn("Type=oneshot", svc_text)
        self.assertNotIn("coordinator tick", svc_text)

        timer = next(a for a in assets if a.template_relpath == "core/systemd/__INSTANCE__-manager.timer.tmpl")
        timer_text = timer.template_path.read_text(encoding="utf-8")
        self.assertFalse(timer.deploy)
        self.assertTrue(timer.deprecated)
        self.assertIn("Deprecated", timer_text)

        env = next(a for a in assets if a.template_relpath == "core/runtime/__INSTANCE__-manager.env.tmpl")
        self.assertEqual(env.required_keys, ("PSC_CONTROL_ROOT",))
        self.assertIn("PSC_CONTROL_ROOT=", env.template_path.read_text(encoding="utf-8"))
        self.assertNotIn("PSC_MANAGER_EXECUTOR=", env.template_path.read_text(encoding="utf-8"))

        target = resolve_template_target("core/systemd/__INSTANCE__-manager.service.tmpl", instance_name="demo-agent")
        self.assertEqual(target, "core/systemd/demo-agent-manager.service")

    def test_dream_cost_and_telegram_units_follow_service_script_contract(self) -> None:
        assets = {asset.template_relpath: asset for asset in list_template_assets()}
        expected = {
            "core/systemd/__INSTANCE__-dream.service.tmpl": {
                "script": "service-dream.sh",
                "env_catalog": ("core/runtime/__INSTANCE__.env", "core/runtime/__INSTANCE__-dream.env"),
            },
            "core/systemd/__INSTANCE__-cost.service.tmpl": {
                "script": "service-cost.sh",
                "env_catalog": ("core/runtime/__INSTANCE__.env", "core/runtime/__INSTANCE__-cost.env"),
            },
            "core/systemd/__INSTANCE__-telegram.service.tmpl": {
                "script": "service-bot.sh",
                "env_catalog": (
                    "core/runtime/__INSTANCE__.env",
                    "core/runtime/__INSTANCE__-telegram.env",
                    "secret/bootstrap/__INSTANCE__.telegram.secret.env",
                ),
            },
        }
        required_lines = (
            "Restart=on-failure",
            "RestartSec=10",
            "StartLimitIntervalSec=300",
            "StartLimitBurst=5",
            "KillMode=control-group",
        )
        for relpath, info in expected.items():
            with self.subTest(template=relpath):
                asset = assets[relpath]
                text = asset.template_path.read_text(encoding="utf-8")
                self.assertEqual(asset.env_catalog, info["env_catalog"])
                for line in required_lines:
                    self.assertIn(line, text)
                self.assertIn(f"ExecStart=/usr/bin/env bash __ROOT_DIR__/scripts/{info['script']}", text)
                self.assertNotIn("/home/", text)

        dream_env = assets["core/runtime/__INSTANCE__-dream.env.tmpl"]
        self.assertEqual(
            dream_env.required_keys,
            ("PSC_MEMORY_ROOT", "PSC_DREAM_INTERVAL_SECONDS", "PSC_EXTRA_CORPUS_ROOT"),
        )

        cost_env = assets["core/runtime/__INSTANCE__-cost.env.tmpl"]
        self.assertEqual(cost_env.required_keys, ("PAULSHACLAW_CONFIG",))


if __name__ == "__main__":
    unittest.main()
