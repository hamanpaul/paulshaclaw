from __future__ import annotations

import json
import subprocess
import sys
import unittest
from tempfile import TemporaryDirectory

from paulshaclaw.deploy import (
    build_command_plan,
    complete_secret_install_flow,
    list_template_assets,
    resolve_template_target,
    validate_plane_permissions,
)


class TemplateMappingTests(unittest.TestCase):
    def test_template_assets_cover_three_planes(self) -> None:
        assets = list_template_assets()
        relpaths = {asset.template_relpath for asset in assets}
        planes = {asset.plane for asset in assets}

        self.assertGreaterEqual(len(assets), 7)
        self.assertTrue({"core", "state", "secret"}.issubset(planes))
        self.assertTrue(
            {
                "core/systemd/__INSTANCE__.service.tmpl",
                "core/systemd/__INSTANCE__-telegram.service.tmpl",
                "core/runtime/__INSTANCE__.env.tmpl",
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


class DeployCliTests(unittest.TestCase):
    def test_cli_subcommands_emit_json_plan(self) -> None:
        with TemporaryDirectory() as tmpdir:
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
                        tmpdir,
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
        self.assertIn("ExecStart=/usr/bin/env bash __ROOT_DIR__/scripts/service-manager.sh", svc_text)
        self.assertIn("Restart=on-failure", svc_text)
        self.assertIn("EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__.env", svc_text)

        timer = next(a for a in assets if a.template_relpath == "core/systemd/__INSTANCE__-manager.timer.tmpl")
        timer_text = timer.template_path.read_text(encoding="utf-8")
        self.assertIn("OnUnitActiveSec", timer_text)
        self.assertIn("DEPRECATED", timer_text)
        self.assertTrue(timer.deprecated)
        self.assertFalse(timer.deploy_enabled)

        env = next(a for a in assets if a.template_relpath == "core/runtime/__INSTANCE__-manager.env.tmpl")
        env_text = env.template_path.read_text(encoding="utf-8")
        self.assertIn("PSC_MANAGER_EXECUTOR=", env_text)
        self.assertIn("PSC_CONTROL_ROOT=", env_text)

        target = resolve_template_target("core/systemd/__INSTANCE__-manager.service.tmpl", instance_name="demo-agent")
        self.assertEqual(target, "core/systemd/demo-agent-manager.service")


class AlwaysOnSystemdTemplateTests(unittest.TestCase):
    def test_always_on_service_templates_and_env_catalog_are_present(self) -> None:
        assets = list_template_assets()
        relpaths = {a.template_relpath for a in assets}
        self.assertIn("core/systemd/__INSTANCE__-dream.service.tmpl", relpaths)
        self.assertIn("core/systemd/__INSTANCE__-cost.service.tmpl", relpaths)
        self.assertIn("core/runtime/__INSTANCE__-dream.env.tmpl", relpaths)
        self.assertIn("core/runtime/__INSTANCE__-cost.env.tmpl", relpaths)

    def test_install_plan_does_not_deploy_deprecated_manager_timer(self) -> None:
        plan = build_command_plan("install", instance_name="demo-agent", root_dir="/srv/paulshaclaw")
        rendered = {asset.target_path for asset in plan.templates}
        self.assertNotIn("core/systemd/demo-agent-manager.timer", rendered)

    def test_service_units_use_root_dir_scripts_and_hardened_restart_policy(self) -> None:
        cases = {
            "core/systemd/__INSTANCE__-dream.service.tmpl": "service-dream.sh",
            "core/systemd/__INSTANCE__-cost.service.tmpl": "service-cost.sh",
            "core/systemd/__INSTANCE__-manager.service.tmpl": "service-manager.sh",
            "core/systemd/__INSTANCE__-telegram.service.tmpl": "service-bot.sh",
        }
        for relpath, script_name in cases.items():
            with self.subTest(relpath=relpath):
                text = next(
                    asset.template_path.read_text(encoding="utf-8")
                    for asset in list_template_assets()
                    if asset.template_relpath == relpath
                )
                self.assertIn("Restart=on-failure", text)
                self.assertIn("RestartSec=10", text)
                self.assertIn("StartLimitIntervalSec=300", text)
                self.assertIn("StartLimitBurst=5", text)
                self.assertIn("KillMode=control-group", text)
                self.assertIn(f"ExecStart=/usr/bin/env bash __ROOT_DIR__/scripts/{script_name}", text)
                self.assertNotIn("/home/", text)

    def test_manager_timer_template_is_marked_deprecated(self) -> None:
        text = (
            next(
                asset.template_path
                for asset in list_template_assets()
                if asset.template_relpath == "core/systemd/__INSTANCE__-manager.timer.tmpl"
            )
            .read_text(encoding="utf-8")
        )
        self.assertIn("DEPRECATED", text)


if __name__ == "__main__":
    unittest.main()
