import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class FakeTmateManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def status(self) -> dict[str, object]:
        self.calls.append("status")
        return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}

    def start(self) -> dict[str, object]:
        self.calls.append("start")
        return {"ok": True, "kind": "tmate", "state": "running", "running": True}

    def stop(self) -> dict[str, object]:
        self.calls.append("stop")
        return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}

    def cleanup_idle(self) -> dict[str, object]:
        self.calls.append("cleanup_idle")
        return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}


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

    def test_daemon_route_to_agent_sends_message_when_agent_running(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        with (
            mock.patch.object(daemon, "_detect_agent_process", return_value=("%9", 4242)),
            mock.patch.object(daemon, "_send_to_pane", return_value={"ok": True, "pane_id": "%9", "sent": "ignored"}) as send_mock,
        ):
            result = daemon.route_to_agent(user_id=1001, text="請幫我整理狀態")

        self.assertEqual(result, "…")
        self.assertEqual(daemon._agent_pane_id, "%9")
        send_mock.assert_called_once_with("%9", "[user:1001] 請幫我整理狀態")

    def test_daemon_route_to_agent_returns_fallback_when_agent_stopped(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._agent_pane_id = "%9"

        with (
            mock.patch.object(daemon, "_detect_agent_process", return_value=None),
            mock.patch.object(daemon, "_send_to_pane") as send_mock,
        ):
            result = daemon.route_to_agent(user_id=1001, text="請幫我整理狀態")

        self.assertEqual(result, "agent 未啟用，請使用 /agent start")
        self.assertIsNone(daemon._agent_pane_id)
        send_mock.assert_not_called()

    def test_telegram_router_routes_authorized_non_slash_text_to_agent(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        with mock.patch.object(daemon, "route_to_agent", return_value="…") as route_mock:
            result = router.handle_message(user_id=1001, text="請幫我整理狀態")

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "…")
        route_mock.assert_called_once_with(user_id=1001, text="請幫我整理狀態")

    def test_telegram_router_surfaces_non_slash_agent_routing_error(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        with mock.patch.object(daemon, "route_to_agent", side_effect=ValueError("tmux not found")):
            result = router.handle_message(user_id=1001, text="請幫我整理狀態")

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "tmux not found")

    def test_telegram_router_keeps_authorized_slash_command_on_daemon_path(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        with mock.patch.object(daemon, "route_to_agent") as route_mock:
            result = router.handle_message(user_id=1001, text="  /status")

        self.assertTrue(result["ok"])
        self.assertIn("PaulShiaBro", result["message"])
        route_mock.assert_not_called()

    def test_telegram_router_rejects_unauthorized_non_slash_text_before_agent_routing(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        with mock.patch.object(daemon, "route_to_agent") as route_mock:
            result = router.handle_message(user_id=9999, text="請幫我整理狀態")

        self.assertFalse(result["ok"])
        self.assertIn("未授權", result["message"])
        route_mock.assert_not_called()

    def test_global_sample_yaml_omits_legacy_chat_provider_shape(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "paulshaclaw" / "config" / "paulshaclaw.sample.yaml"

        text = sample.read_text(encoding="utf-8")

        self.assertNotIn("chat:", text)
        self.assertNotIn("openai_compatible:", text)
        self.assertNotIn("OPENAI_BASE_URL", text)
        self.assertNotIn("OPENAI_API_KEY", text)

    def test_help_command_lists_runtime_commands(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        result = router.handle_message(user_id=1001, text="/help")

        self.assertTrue(result["ok"])
        self.assertIn("/agent [start|startf|stop|status]", result["message"])
        self.assertIn("/tmate [status|start|stop]", result["message"])
        self.assertIn("/dispatch <task_id>|<pane_id> <message>", result["message"])

    def test_tmate_bare_command_returns_status(self) -> None:
        config_path = self.make_config_path()
        tmate_manager = FakeTmateManager()
        daemon = PaulShiaBroDaemon(
            config=load_config(config_path=config_path),
            coordinator=FakeCoordinator(),
            tmate_manager=tmate_manager,
        )
        router = TelegramCommandRouter(daemon=daemon)

        result = router.handle_message(user_id=1001, text="/tmate")

        self.assertTrue(result["ok"])
        self.assertEqual(tmate_manager.calls, ["status"])
        self.assertIn("tmate: stopped", result["message"])

    def test_agent_status_reports_running_state(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        with mock.patch.object(daemon, "_detect_agent_process", return_value=("%9", 4242)):
            result = daemon.handle_command("/agent status")

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "agent")
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["running"])
        self.assertEqual(result["pane_id"], "%9")
        self.assertEqual(result["pid"], 4242)

    def test_agent_status_reports_stopped_state(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._agent_pane_id = "%9"

        with mock.patch.object(daemon, "_detect_agent_process", return_value=None):
            result = daemon.handle_command("/agent status")

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "agent")
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["running"])
        self.assertNotIn("pane_id", result)
        self.assertNotIn("pid", result)
        self.assertIsNone(daemon._agent_pane_id)

    def test_agent_start_returns_existing_process_without_creating_new_pane(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._cockpit_pane_id = "%1"

        with (
            mock.patch.object(daemon, "_detect_agent_process", return_value=("%9", 4242)),
            mock.patch("paulshaclaw.core.daemon.subprocess.run") as run_mock,
        ):
            result = daemon.handle_command("/agent start")

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["already_running"])
        self.assertEqual(result["pane_id"], "%9")
        self.assertEqual(result["pid"], 4242)
        self.assertEqual(daemon._agent_pane_id, "%9")
        run_mock.assert_not_called()

    def test_agent_start_creates_split_window_and_remembers_pane(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._cockpit_pane_id = "%1"

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            expected_prefix = ["tmux", "split-window", "-h", "-t", "%1", "-P", "-F", "#{pane_id}"]
            self.assertEqual(command[:8], expected_prefix)
            self.assertTrue(command[8].endswith("claude-gemma4"))
            return subprocess.CompletedProcess(command, 0, stdout="%9\n", stderr="")

        with (
            mock.patch.object(daemon, "_detect_agent_process", return_value=None),
            mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=fake_run),
        ):
            result = daemon.handle_command("/agent start")

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["started"])
        self.assertEqual(result["pane_id"], "%9")
        self.assertEqual(daemon._agent_pane_id, "%9")

    def test_agent_startf_launches_force_flag(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._cockpit_pane_id = "%1"

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command[:8], ["tmux", "split-window", "-h", "-t", "%1", "-P", "-F", "#{pane_id}"])
            self.assertTrue(command[8].endswith("claude-gemma4 -f"))
            return subprocess.CompletedProcess(command, 0, stdout="%10\n", stderr="")

        with (
            mock.patch.object(daemon, "_detect_agent_process", return_value=None),
            mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=fake_run),
        ):
            result = daemon.handle_command("/agent startf")

        self.assertTrue(result["ok"])
        self.assertEqual(result["pane_id"], "%10")
        self.assertEqual(daemon._agent_pane_id, "%10")

    def test_agent_stop_sends_exit_and_clears_agent_pane(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._agent_pane_id = "%9"

        with (
            mock.patch.object(daemon, "_detect_agent_process", side_effect=[("%9", 4242), None]) as detect_mock,
            mock.patch.object(daemon, "_send_to_pane", return_value={"ok": True, "pane_id": "%9", "sent": "exit"}) as send_mock,
        ):
            result = daemon.handle_command("/agent stop")

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["running"])
        self.assertTrue(result["stopped"])
        self.assertEqual(result["pane_id"], "%9")
        self.assertEqual(result["pid"], 4242)
        self.assertIsNone(daemon._agent_pane_id)
        send_mock.assert_called_once_with("%9", "exit")
        self.assertEqual(detect_mock.call_count, 2)

    def test_agent_stop_reports_running_when_exit_does_not_take_effect_immediately(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._agent_pane_id = "%9"

        with (
            mock.patch.object(daemon, "_detect_agent_process", side_effect=[("%9", 4242), ("%9", 4242), ("%9", 4242)]) as detect_mock,
            mock.patch.object(daemon, "_send_to_pane", return_value={"ok": True, "pane_id": "%9", "sent": "exit"}) as send_mock,
        ):
            result = daemon.handle_command("/agent stop")

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["running"])
        self.assertNotIn("stopped", result)
        self.assertEqual(result["pane_id"], "%9")
        self.assertEqual(result["pid"], 4242)
        self.assertEqual(daemon._agent_pane_id, "%9")
        send_mock.assert_called_once_with("%9", "exit")
        self.assertEqual(detect_mock.call_count, 3)

    def test_agent_stop_returns_already_stopped_when_no_agent_exists(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        with mock.patch.object(daemon, "_detect_agent_process", return_value=None):
            result = daemon.handle_command("/agent stop")

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["running"])
        self.assertTrue(result["already_stopped"])
        self.assertIsNone(daemon._agent_pane_id)

    def test_agent_start_errors_when_cockpit_pane_is_unavailable(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        with mock.patch.object(daemon, "_detect_agent_process", return_value=None):
            with self.assertRaisesRegex(ValueError, "cockpit pane"):
                daemon.handle_command("/agent start")

    def test_agent_start_errors_when_tmux_is_unavailable(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        daemon._cockpit_pane_id = "%1"

        with (
            mock.patch.object(daemon, "_detect_agent_process", return_value=None),
            mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=FileNotFoundError),
        ):
            with self.assertRaisesRegex(ValueError, "tmux unavailable"):
                daemon.handle_command("/agent start")

    def test_detect_agent_process_returns_none_when_tmux_is_unavailable(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        with mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=FileNotFoundError):
            result = daemon._detect_agent_process()

        self.assertIsNone(result)

    def test_detect_agent_process_returns_none_when_no_agent_process_exists(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command == ["tmux", "list-panes", "-a", "-F", "#{pane_id} #{pane_pid}"]:
                return subprocess.CompletedProcess(command, 0, stdout="%1 101\n%2 202\n", stderr="")
            if command == ["ps", "-p", "101", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="bash\n", stderr="")
            if command == ["pgrep", "-P", "101", "-a"]:
                return subprocess.CompletedProcess(command, 0, stdout="111 bash\n", stderr="")
            if command == ["ps", "-p", "111", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="bash\n", stderr="")
            if command == ["pgrep", "-P", "111", "-a"]:
                raise subprocess.CalledProcessError(1, command, output="", stderr="")
            if command == ["ps", "-p", "202", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="bash\n", stderr="")
            if command == ["pgrep", "-P", "202", "-a"]:
                return subprocess.CompletedProcess(command, 0, stdout="212 python\n", stderr="")
            if command == ["ps", "-p", "212", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="python\n", stderr="")
            if command == ["pgrep", "-P", "212", "-a"]:
                raise subprocess.CalledProcessError(1, command, output="", stderr="")
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=fake_run):
            result = daemon._detect_agent_process()

        self.assertIsNone(result)

    def test_detect_agent_process_returns_pane_and_pid_for_nested_agent_process(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command == ["tmux", "list-panes", "-a", "-F", "#{pane_id} #{pane_pid}"]:
                return subprocess.CompletedProcess(command, 0, stdout="%1 101\n%2 202\n", stderr="")
            if command == ["ps", "-p", "101", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="bash\n", stderr="")
            if command == ["pgrep", "-P", "101", "-a"]:
                return subprocess.CompletedProcess(command, 0, stdout="111 bash\n", stderr="")
            if command == ["ps", "-p", "111", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="bash\n", stderr="")
            if command == ["pgrep", "-P", "111", "-a"]:
                return subprocess.CompletedProcess(command, 0, stdout="112 claude-gemma4 --project stage1\n", stderr="")
            if command == ["ps", "-p", "112", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="claude-gemma4 --project stage1\n", stderr="")
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=fake_run):
            result = daemon._detect_agent_process()

        self.assertEqual(result, ("%1", 112))

    def test_detect_agent_process_prefers_agent_over_proxy_process(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command == ["tmux", "list-panes", "-a", "-F", "#{pane_id} #{pane_pid}"]:
                return subprocess.CompletedProcess(command, 0, stdout="%1 101\n", stderr="")
            if command == ["ps", "-p", "101", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="bash\n", stderr="")
            if command == ["pgrep", "-P", "101", "-a"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=(
                        "111 python /repo/scripts/claude-gemma4-proxy\n"
                        "112 /opt/claude/bin/claude.exe --settings /home/paul_chen/.claude-gemma4/settings.json\n"
                    ),
                    stderr="",
                )
            if command == ["ps", "-p", "111", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="python /repo/scripts/claude-gemma4-proxy\n", stderr="")
            if command == ["ps", "-p", "112", "-o", "args="]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="/opt/claude/bin/claude.exe --settings /home/paul_chen/.claude-gemma4/settings.json\n",
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=fake_run):
            result = daemon._detect_agent_process()

        self.assertEqual(result, ("%1", 112))

    def test_detect_agent_process_returns_pane_and_pid_when_pane_root_is_agent(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command == ["tmux", "list-panes", "-a", "-F", "#{pane_id} #{pane_pid}"]:
                return subprocess.CompletedProcess(command, 0, stdout="%1 101\n", stderr="")
            if command == ["ps", "-p", "101", "-o", "args="]:
                return subprocess.CompletedProcess(command, 0, stdout="/repo/scripts/claude-gemma4 --project stage1\n", stderr="")
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch("paulshaclaw.core.daemon.subprocess.run", side_effect=fake_run):
            result = daemon._detect_agent_process()

        self.assertEqual(result, ("%1", 101))

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
