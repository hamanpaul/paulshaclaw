import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from paulshaclaw.bot.telegram import TelegramCommandRouter
from paulshaclaw.core.config import load_config
from paulshaclaw.core.daemon import PaulShiaBroDaemon
from paulshaclaw.tui.view import render_pane_task_view


class FakeCoordinator:
    def __init__(self) -> None:
        self.calls = []

    def create_job(self, *, phase: str, scope: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(
            {
                "phase": phase,
                "scope": scope,
                "payload": payload,
            }
        )
        return {
            "job_id": f"job-{len(self.calls)}",
            "phase": phase,
            "scope": scope,
        }


def write_config_file() -> Path:
    config = {
        "daemon_name": "PaulShiaBro",
        "default_project": "stage1-demo",
        "allowed_user_ids": [1001],
        "coordinator": {
            "phase": "build",
            "default_payload": {
                "source": "stage1-smoke",
            },
        },
        "pane_assignments": [
            {
                "pane_id": "%1",
                "title": "manager",
                "task_id": "stage1-core",
                "status": "running",
            },
            {
                "pane_id": "%2",
                "title": "tester",
                "task_id": "stage1-smoke",
                "status": "idle",
            },
        ],
    }

    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(config, handle)
        handle.flush()
    finally:
        handle.close()
    return Path(handle.name)


class Stage1SmokeTest(unittest.TestCase):
    def make_config_path(self) -> Path:
        config_path = write_config_file()
        self.addCleanup(config_path.unlink, missing_ok=True)
        return config_path

    def test_daemon_loads_config_and_returns_status(self) -> None:
        config_path = self.make_config_path()
        config = load_config(config_path=config_path)
        daemon = PaulShiaBroDaemon(config=config, coordinator=FakeCoordinator())

        result = daemon.handle_command("/status")

        self.assertTrue(result["ok"])
        self.assertEqual(result["daemon"], "PaulShiaBro")
        self.assertEqual(result["project"], "stage1-demo")
        self.assertEqual(result["pane_count"], 2)

    def test_load_config_supports_env_fallback(self) -> None:
        config_path = self.make_config_path()
        previous = os.environ.get("PSC_STAGE1_CONFIG")
        os.environ["PSC_STAGE1_CONFIG"] = str(config_path)
        try:
            config = load_config()
        finally:
            if previous is None:
                os.environ.pop("PSC_STAGE1_CONFIG", None)
            else:
                os.environ["PSC_STAGE1_CONFIG"] = previous

        self.assertEqual(config.daemon_name, "PaulShiaBro")
        self.assertEqual(config.default_project, "stage1-demo")

    def test_load_config_rejects_missing_required_fields(self) -> None:
        config = {
            "default_project": "stage1-demo",
            "allowed_user_ids": [1001],
            "coordinator": {
                "phase": "build",
                "default_payload": {
                    "source": "stage1-smoke",
                },
            },
            "pane_assignments": [],
        }
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        try:
            json.dump(config, handle)
            handle.flush()
        finally:
            handle.close()
        config_path = Path(handle.name)
        self.addCleanup(config_path.unlink, missing_ok=True)

        with self.assertRaisesRegex(ValueError, "config.daemon_name 缺失"):
            load_config(config_path=config_path)

    def test_dispatch_command_calls_coordinator(self) -> None:
        config_path = self.make_config_path()
        coordinator = FakeCoordinator()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=coordinator)

        result = daemon.handle_command("/dispatch stage1-smoke")

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(coordinator.calls[0]["scope"], "stage1-smoke")
        self.assertEqual(coordinator.calls[0]["payload"]["source"], "stage1-smoke")

    def test_sample_config_file_loads(self) -> None:
        sample_config = Path(__file__).resolve().parents[1] / "config" / "paulshaclaw-stage1.sample.json"

        config = load_config(config_path=sample_config)

        self.assertEqual(config.daemon_name, "PaulShiaBro")
        self.assertEqual(config.default_project, "stage1-demo")

    def test_tui_view_lists_panes_and_tasks(self) -> None:
        config_path = self.make_config_path()
        config = load_config(config_path=config_path)

        rendered = render_pane_task_view(config)

        self.assertIn("pane", rendered.lower())
        self.assertIn("%1", rendered)
        self.assertIn("stage1-core", rendered)
        self.assertIn("stage1-smoke", rendered)

    def test_telegram_router_rejects_unauthorized_user(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        rejected = router.handle_message(user_id=9999, text="/status")
        accepted = router.handle_message(user_id=1001, text="/status")

        self.assertFalse(rejected["ok"])
        self.assertIn("未授權", rejected["message"])
        self.assertTrue(accepted["ok"])
        self.assertIn("PaulShiaBro", accepted["message"])

    def test_telegram_router_surfaces_invalid_command(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        result = router.handle_message(user_id=1001, text="/unknown")

        self.assertFalse(result["ok"])
        self.assertIn("不支援的指令", result["message"])

    def test_telegram_router_dispatches_authorized_command(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        result = router.handle_message(user_id=1001, text="/dispatch stage1-smoke")

        self.assertTrue(result["ok"])
        self.assertIn("job-1", result["message"])
        self.assertEqual(result["result"]["scope"], "stage1-smoke")

    def test_cli_entry_outputs_json_status(self) -> None:
        config_path = self.make_config_path()

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paulshaclaw.core.daemon",
                "--config",
                str(config_path),
                "--command",
                "/status",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["daemon"], "PaulShiaBro")

    def test_cli_entry_supports_env_config(self) -> None:
        config_path = self.make_config_path()
        env = dict(os.environ)
        env["PSC_STAGE1_CONFIG"] = str(config_path)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paulshaclaw.core.daemon",
                "--command",
                "/status",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["project"], "stage1-demo")

    def test_cli_entry_returns_clean_error_for_invalid_command(self) -> None:
        config_path = self.make_config_path()
        env = dict(os.environ)
        env["PSC_STAGE1_CONFIG"] = str(config_path)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paulshaclaw.core.daemon",
                "--command",
                "/unknown",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("不支援的指令", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
