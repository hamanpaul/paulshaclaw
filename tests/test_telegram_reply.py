from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request
from unittest import mock

from paulshaclaw.bot.listener import BotSettings, TelegramApiClient, TelegramApiError, TelegramListener, build_listener
from paulshaclaw.bot.reply import main as reply_main
from paulshaclaw.bot.reply import (
    TelegramChatBindingStore,
    TelegramReplyBridge,
    ReplyTarget,
)


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


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
        self.calls.append({"user_id": user_id, "text": text})
        return {"ok": True, "message": "ok"}


class TelegramChatBindingStoreTests(unittest.TestCase):
    def test_remember_and_reload_binding_by_user_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TelegramChatBindingStore(Path(tmpdir) / "bindings.json")

            store.remember(user_id=7, chat_id=1001)
            store.remember(user_id=8, chat_id=1002)

            reloaded = TelegramChatBindingStore(store.path)
            self.assertEqual(reloaded.lookup_chat_id(7), 1001)
            self.assertEqual(reloaded.lookup_chat_id(8), 1002)


class TelegramReplyBridgeTests(unittest.TestCase):
    def test_reply_sends_only_to_bound_source_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TelegramChatBindingStore(Path(tmpdir) / "bindings.json")
            store.remember(user_id=7, chat_id=1001)
            store.remember(user_id=8, chat_id=1002)
            opener = FakeOpener(
                [
                    {"ok": True, "result": {"message_id": 1}},
                ]
            )
            client = TelegramApiClient("fake-token", opener=opener)
            bridge = TelegramReplyBridge(client=client, bindings=store, allowed_user_ids=(7, 8))

            targets = bridge.reply(text="PaulShiaBro 已收到", source_user_id=7)

            self.assertEqual(targets, [ReplyTarget(user_id=7, chat_id=1001)])
            self.assertEqual(json.loads(opener.requests[0]["data"].decode("utf-8")), {"chat_id": 1001, "text": "PaulShiaBro 已收到"})

    def test_reply_without_source_user_fans_out_to_all_bound_allowed_users(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TelegramChatBindingStore(Path(tmpdir) / "bindings.json")
            store.remember(user_id=7, chat_id=1001)
            store.remember(user_id=8, chat_id=1002)
            opener = FakeOpener(
                [
                    {"ok": True, "result": {"message_id": 1}},
                    {"ok": True, "result": {"message_id": 2}},
                ]
            )
            client = TelegramApiClient("fake-token", opener=opener)
            bridge = TelegramReplyBridge(client=client, bindings=store, allowed_user_ids=(7, 8, 9))

            targets = bridge.reply(text="PaulShiaBro 廣播", source_user_id=None)

            self.assertEqual(targets, [ReplyTarget(user_id=7, chat_id=1001), ReplyTarget(user_id=8, chat_id=1002)])
            payloads = [json.loads(item["data"].decode("utf-8")) for item in opener.requests]
            self.assertEqual(
                payloads,
                [
                    {"chat_id": 1001, "text": "PaulShiaBro 廣播"},
                    {"chat_id": 1002, "text": "PaulShiaBro 廣播"},
                ],
            )

    def test_reply_rejects_source_user_without_bound_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TelegramChatBindingStore(Path(tmpdir) / "bindings.json")
            opener = FakeOpener([])
            client = TelegramApiClient("fake-token", opener=opener)
            bridge = TelegramReplyBridge(client=client, bindings=store, allowed_user_ids=(7,))

            with self.assertRaisesRegex(ValueError, "找不到 source user 7 對應的 Telegram chat 綁定"):
                bridge.reply(text="hello", source_user_id=7)


class TelegramListenerBindingTests(unittest.TestCase):
    def test_process_update_records_user_chat_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TelegramChatBindingStore(Path(tmpdir) / "bindings.json")
            listener = TelegramListener(
                client=mock.Mock(),
                router=FakeRouter(),
                bindings=store,
            )
            listener.client.send_message = mock.Mock()

            listener.process_update(
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 1001, "type": "private"},
                        "from": {"id": 7},
                        "text": "/status",
                    },
                }
            )

            self.assertEqual(store.lookup_chat_id(7), 1001)

    def test_process_update_does_not_record_group_chat_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TelegramChatBindingStore(Path(tmpdir) / "bindings.json")
            listener = TelegramListener(
                client=mock.Mock(),
                router=FakeRouter(),
                bindings=store,
            )
            listener.client.send_message = mock.Mock()

            listener.process_update(
                {
                    "update_id": 2,
                    "message": {
                        "chat": {"id": -100123, "type": "group"},
                        "from": {"id": 7},
                        "text": "group ping",
                    },
                }
            )

            self.assertIsNone(store.lookup_chat_id(7))

    def test_process_update_continues_when_binding_store_is_corrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bindings.json"
            path.write_text("{not-json", encoding="utf-8")
            store = TelegramChatBindingStore(path)
            client = mock.Mock()
            listener = TelegramListener(
                client=client,
                router=FakeRouter(),
                bindings=store,
            )
            client.send_message = mock.Mock()

            with self.assertLogs("paulshaclaw.bot.listener", level="ERROR") as captured:
                listener.process_update(
                    {
                        "update_id": 3,
                        "message": {
                            "chat": {"id": 1001, "type": "private"},
                            "from": {"id": 7},
                            "text": "/status",
                        },
                    }
                )

            client.send_message.assert_called_once_with(chat_id=1001, text="ok")
            self.assertIn("BINDING_SAVE_ERROR", "\n".join(captured.output))


class TelegramReplyCliTests(unittest.TestCase):
    def test_reply_main_echoes_sent_content(self) -> None:
        bridge = mock.Mock()
        bridge.reply.return_value = [ReplyTarget(user_id=7, chat_id=1001)]
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            mock.patch("paulshaclaw.bot.reply.build_reply_bridge", return_value=bridge),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            exit_code = reply_main(
                [
                    "--text",
                    "PaulShiaBro 會透過 Telegram 回覆這段",
                    "--source-user-id",
                    "7",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("已送出到 user=7 chat=1001", stdout.getvalue())
        self.assertIn("PaulShiaBro 會透過 Telegram 回覆這段", stdout.getvalue())
        bridge.reply.assert_called_once_with(text="PaulShiaBro 會透過 Telegram 回覆這段", source_user_id=7)

    def test_reply_main_returns_clean_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            mock.patch("paulshaclaw.bot.reply.build_reply_bridge", side_effect=TelegramApiError("Bad Request")),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            exit_code = reply_main(["--text", "hello"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("錯誤: Bad Request", stderr.getvalue())


class TelegramReplyRuntimeWiringTests(unittest.TestCase):
    def test_build_listener_wires_binding_store_for_runtime_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "daemon_name": "psc",
                        "default_project": "demo",
                        "allowed_user_ids": [7],
                        "coordinator": {"phase": "stage1", "default_payload": {}},
                        "pane_assignments": [
                            {"pane_id": "%0", "title": "cockpit", "task_id": "task-1", "status": "ready"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            bindings_path = Path(tmpdir) / "bindings.json"

            with mock.patch.dict(os.environ, {"PSC_TELEGRAM_BINDINGS_PATH": str(bindings_path)}, clear=False):
                listener = build_listener(
                    config_path=str(config_path),
                    settings=BotSettings(token="fake-token"),
                    client=mock.Mock(),
                )
                listener.client.send_message = mock.Mock()
                listener.process_update(
                    {
                        "update_id": 1,
                        "message": {
                            "chat": {"id": 1001, "type": "private"},
                            "from": {"id": 7},
                            "text": "/status",
                        },
                    }
                )

            payload = json.loads(bindings_path.read_text(encoding="utf-8"))
            self.assertEqual(payload, {"7": 1001})

    def test_build_listener_does_not_persist_unauthorized_private_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "daemon_name": "psc",
                        "default_project": "demo",
                        "allowed_user_ids": [7],
                        "coordinator": {"phase": "stage1", "default_payload": {}},
                        "pane_assignments": [
                            {"pane_id": "%0", "title": "cockpit", "task_id": "task-1", "status": "ready"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            bindings_path = Path(tmpdir) / "bindings.json"

            with mock.patch.dict(os.environ, {"PSC_TELEGRAM_BINDINGS_PATH": str(bindings_path)}, clear=False):
                listener = build_listener(
                    config_path=str(config_path),
                    settings=BotSettings(token="fake-token"),
                    client=mock.Mock(),
                )
                listener.client.send_message = mock.Mock()
                listener.process_update(
                    {
                        "update_id": 2,
                        "message": {
                            "chat": {"id": 9999, "type": "private"},
                            "from": {"id": 1234},
                            "text": "/status",
                        },
                    }
                )

            self.assertFalse(bindings_path.exists())
