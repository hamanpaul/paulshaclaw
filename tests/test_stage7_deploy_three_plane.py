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


if __name__ == "__main__":
    unittest.main()
