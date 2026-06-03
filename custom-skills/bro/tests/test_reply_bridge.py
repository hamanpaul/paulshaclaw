from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request
from unittest import mock

import importlib.util


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "reply_bridge.py"
SPEC = importlib.util.spec_from_file_location("reply_bridge", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
reply_bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reply_bridge
SPEC.loader.exec_module(reply_bridge)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        self.requests.append(
            {
                "url": request.full_url,
                "data": request.data or b"",
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("no fake response queued")
        return FakeResponse(self.responses.pop(0))


class ReplyBridgeTests(unittest.TestCase):
    def _write_runtime_files(self, tmpdir: str) -> tuple[Path, Path, Path]:
        config_path = Path(tmpdir) / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "daemon_name": "psc",
                    "default_project": "demo",
                    "allowed_user_ids": [7, 8],
                    "coordinator": {"phase": "stage1", "default_payload": {}},
                    "pane_assignments": [
                        {"pane_id": "%0", "title": "cockpit", "task_id": "task-1", "status": "ready"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        secret_env_path = Path(tmpdir) / "telegram.env"
        secret_env_path.write_text("PSC_TELEGRAM_BOT_TOKEN=fake-token\n", encoding="utf-8")
        bindings_path = Path(tmpdir) / "bindings.json"
        bindings_path.write_text(json.dumps({"7": 1001, "8": 1002}), encoding="utf-8")
        return config_path, secret_env_path, bindings_path

    def test_send_reply_uses_bound_source_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path, secret_env_path, bindings_path = self._write_runtime_files(tmpdir)
            opener = FakeOpener([{"ok": True, "result": {"message_id": 1}}])

            targets = reply_bridge.send_reply(
                text="skill-local reply",
                source_user_id=7,
                config_path=config_path,
                secret_env_path=secret_env_path,
                bindings_path=bindings_path,
                opener=opener,
            )

            self.assertEqual(targets, [reply_bridge.ReplyTarget(user_id=7, chat_id=1001)])
            self.assertEqual(
                json.loads(opener.requests[0]["data"].decode("utf-8")),
                {"chat_id": 1001, "text": "skill-local reply"},
            )

    def test_send_reply_dry_run_avoids_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path, secret_env_path, bindings_path = self._write_runtime_files(tmpdir)

            targets = reply_bridge.send_reply(
                text="dry run",
                source_user_id=None,
                config_path=config_path,
                secret_env_path=secret_env_path,
                bindings_path=bindings_path,
                dry_run=True,
            )

            self.assertEqual(
                targets,
                [
                    reply_bridge.ReplyTarget(user_id=7, chat_id=1001),
                    reply_bridge.ReplyTarget(user_id=8, chat_id=1002),
                ],
            )

    def test_main_reports_clean_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(reply_bridge, "send_reply", side_effect=reply_bridge.TelegramApiError("Bad Request")),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            exit_code = reply_bridge.main(["--text", "hello"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("錯誤: Bad Request", stderr.getvalue())
