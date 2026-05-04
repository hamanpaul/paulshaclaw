from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from paulshaclaw.core.tmate import TmateManager
from paulshaclaw.core.tmate import default_tmate_executor


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []
        self.responses: dict[tuple[str, ...], list[object]] = defaultdict(list)

    def queue(self, argv: list[str], response: object) -> None:
        self.responses[tuple(argv)].append(response)

    def __call__(self, argv: list[str], timeout: int) -> str:
        self.calls.append((list(argv), timeout))
        queued = self.responses[tuple(argv)]
        if not queued:
            raise AssertionError(f"Unexpected call: {argv}")
        response = queued.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response()
        return response


class Stage1TmateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("tests/.stage1_tmate_artifacts") / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def make_manager(self, executor: FakeExecutor, now: datetime) -> TmateManager:
        return TmateManager(
            executor=executor,
            now=lambda: now,
            socket_path=self.root / "run" / "paulshaclaw-tmate.sock",
            state_path=self.root / "state" / "tmate.json",
        )

    def test_status_returns_stopped_when_session_absent(self) -> None:
        executor = FakeExecutor()
        executor.queue(["tmate", "-S", str(self.root / "run" / "paulshaclaw-tmate.sock"), "has-session", "-t", "paulshaclaw"], ValueError("session absent"))
        manager = self.make_manager(executor, datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc))

        self.assertEqual(manager.status(), {"ok": True, "kind": "tmate", "state": "stopped", "running": False})
        self.assertFalse(manager.state_path.exists())

    def test_start_creates_session_links_and_state_file(self) -> None:
        now = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        executor = FakeExecutor()
        socket = str(self.root / "run" / "paulshaclaw-tmate.sock")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], ValueError("session absent"))
        executor.queue(["tmate", "-S", socket, "new-session", "-d", "-s", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{session_attached}"], "1")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_ssh}"], "ssh rw")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_web}"], "web rw")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_ssh_ro}"], "ssh ro")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_web_ro}"], "web ro")
        manager = self.make_manager(executor, now)

        result = manager.start()

        self.assertEqual(result, {
            "ok": True,
            "kind": "tmate",
            "state": "running",
            "running": True,
            "ssh": "ssh rw",
            "web": "web rw",
            "ssh_ro": "ssh ro",
            "web_ro": "web ro",
            "attached_clients": 1,
            "timeout_seconds": 3600,
        })
        self.assertTrue(result["running"])
        self.assertTrue(manager.state_path.exists())
        state = json.loads(manager.state_path.read_text())
        self.assertEqual(state["session_name"], "paulshaclaw")
        self.assertEqual(state["timeout_seconds"], 3600)
        self.assertEqual(state["socket_path"], socket)
        self.assertEqual(state["started_at"], now.isoformat())

    def test_stop_kills_session_and_removes_state_file(self) -> None:
        now = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        executor = FakeExecutor()
        socket = str(self.root / "run" / "paulshaclaw-tmate.sock")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "kill-session", "-t", "paulshaclaw"], "")
        manager = self.make_manager(executor, now)
        manager.state_path.parent.mkdir(parents=True, exist_ok=True)
        manager.state_path.write_text(json.dumps({"session_name": "paulshaclaw"}))

        self.assertEqual(manager.stop(), {"ok": True, "kind": "tmate", "state": "stopped", "running": False})
        self.assertFalse(manager.state_path.exists())

    def test_cleanup_idle_records_first_zero_client_as_running(self) -> None:
        started = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        now = started + timedelta(seconds=10)
        executor = FakeExecutor()
        socket = str(self.root / "run" / "paulshaclaw-tmate.sock")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{session_attached}"], "0")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_ssh}"], "ssh rw")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_web}"], "web rw")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_ssh_ro}"], "ssh ro")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_web_ro}"], "web ro")
        manager = self.make_manager(executor, now)
        manager.state_path.parent.mkdir(parents=True, exist_ok=True)
        manager.state_path.write_text(
            json.dumps(
                {
                    "socket_path": socket,
                    "session_name": "paulshaclaw",
                    "started_at": started.isoformat(),
                    "last_no_client_at": None,
                    "timeout_seconds": 3600,
                }
            )
        )

        result = manager.cleanup_idle()

        self.assertEqual(result, {
            "ok": True,
            "kind": "tmate",
            "state": "running",
            "running": True,
            "ssh": "ssh rw",
            "web": "web rw",
            "ssh_ro": "ssh ro",
            "web_ro": "web ro",
            "attached_clients": 0,
            "timeout_seconds": 3600,
        })
        state = json.loads(manager.state_path.read_text())
        self.assertEqual(state["last_no_client_at"], now.isoformat())

    def test_cleanup_idle_stops_after_timeout_without_clients(self) -> None:
        started = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        idle = started + timedelta(seconds=3600)
        executor = FakeExecutor()
        socket = str(self.root / "run" / "paulshaclaw-tmate.sock")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{session_attached}"], "0")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "kill-session", "-t", "paulshaclaw"], "")
        manager = self.make_manager(executor, idle)
        manager.state_path.parent.mkdir(parents=True, exist_ok=True)
        manager.state_path.write_text(
            json.dumps(
                {
                    "socket_path": socket,
                    "session_name": "paulshaclaw",
                    "started_at": started.isoformat(),
                    "last_no_client_at": started.isoformat(),
                    "timeout_seconds": 3600,
                }
            )
        )

        self.assertEqual(manager.cleanup_idle(), {"ok": True, "kind": "tmate", "state": "stopped", "running": False})
        self.assertFalse(manager.state_path.exists())

    def test_cleanup_idle_clears_idle_marker_when_client_returns(self) -> None:
        started = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        later = started + timedelta(seconds=10)
        executor = FakeExecutor()
        socket = str(self.root / "run" / "paulshaclaw-tmate.sock")
        executor.queue(["tmate", "-S", socket, "has-session", "-t", "paulshaclaw"], "")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{session_attached}"], "1")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_ssh}"], "ssh rw")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_web}"], "web rw")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_ssh_ro}"], "ssh ro")
        executor.queue(["tmate", "-S", socket, "display-message", "-p", "#{tmate_web_ro}"], "web ro")
        manager = self.make_manager(executor, later)
        manager.state_path.parent.mkdir(parents=True, exist_ok=True)
        manager.state_path.write_text(
            json.dumps(
                {
                    "socket_path": socket,
                    "session_name": "paulshaclaw",
                    "started_at": started.isoformat(),
                    "last_no_client_at": started.isoformat(),
                    "timeout_seconds": 3600,
                }
            )
        )

        result = manager.cleanup_idle()

        self.assertEqual(result["state"], "running")
        self.assertTrue(result["running"])
        state = json.loads(manager.state_path.read_text())
        self.assertIsNone(state["last_no_client_at"])

    def test_default_tmate_executor_uses_check_and_strips_output(self) -> None:
        mock_result = Mock(stdout=" hello\n", stderr="", returncode=0)
        with patch("subprocess.run", return_value=mock_result) as run_mock:
            self.assertEqual(default_tmate_executor(["tmate", "status"], 7), "hello")
        run_mock.assert_called_once_with(["tmate", "status"], check=True, capture_output=True, text=True, timeout=7)

    def test_default_tmate_executor_error_messages_are_clean(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            with self.assertRaisesRegex(ValueError, "^tmate not found$"):
                default_tmate_executor(["tmate"], 3)

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["tmate"], timeout=5),
        ):
            with self.assertRaisesRegex(ValueError, "^tmate command timed out after 5s$"):
                default_tmate_executor(["tmate"], 5)

        exc = subprocess.CalledProcessError(2, ["tmate"], stderr="boom\n")
        with patch("subprocess.run", side_effect=exc):
            with self.assertRaisesRegex(ValueError, "^boom$"):
                default_tmate_executor(["tmate"], 3)


if __name__ == "__main__":
    unittest.main()
