from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from urllib.request import Request
from unittest import mock

from paulshaclaw.bot.listener import BotSettings, TelegramApiClient, TelegramApiError, TelegramListener, build_listener
from paulshaclaw.bot.reply import main as reply_main
from paulshaclaw.bot.reply import (
    MessagePaneMap,
    TelegramChatBindingStore,
    TelegramReplyBridge,
    ReplyTarget,
    default_message_pane_map_path,
)

REPLY_BRIDGE = Path(__file__).resolve().parents[1] / "custom-skills" / "bro" / "scripts" / "reply_bridge.py"


def load_reply_bridge():
    import sys
    loader = SourceFileLoader("reply_bridge", str(REPLY_BRIDGE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reply_bridge"] = module
    loader.exec_module(module)
    return module


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

    def handle_message(self, *, user_id: int, text: str, pane_id: str | None = None) -> dict[str, object]:
        self.calls.append({"user_id": user_id, "text": text, "pane_id": pane_id})
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


class ReplyBridgeChunkTests(unittest.TestCase):
    def test_chunk_text_splits_long_text_on_newline(self):
        bridge = load_reply_bridge()
        long_text = ("a" * 3000) + "\n" + ("b" * 3000)
        chunks = bridge._chunk_text(long_text, limit=4000)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), long_text.replace("\n", ""))

    def test_chunk_text_keeps_short_text_single(self):
        bridge = load_reply_bridge()
        self.assertEqual(bridge._chunk_text("hi", limit=4000), ["hi"])

    def test_chunk_text_preserves_blank_line_at_boundary(self):
        # Only the single delimiter newline is consumed; a further blank line survives.
        bridge = load_reply_bridge()
        text = ("a" * 3999) + "\n\n" + ("b" * 10)
        chunks = bridge._chunk_text(text, limit=4000)
        self.assertEqual(chunks, ["a" * 3999, "\n" + "b" * 10])

    def test_chunk_text_hard_split_loses_no_characters(self):
        bridge = load_reply_bridge()
        text = "x" * 9000  # no newline -> hard split
        chunks = bridge._chunk_text(text, limit=4000)
        self.assertEqual("".join(chunks), text)


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
        bridge.reply.assert_called_once_with(
            text="PaulShiaBro 會透過 Telegram 回覆這段",
            source_user_id=7,
            pane_id=mock.ANY,
        )

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


class MessagePaneMapTests(unittest.TestCase):
    def test_remember_and_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = MessagePaneMap(Path(tmpdir) / "map.json")
            m.remember(message_id=42, pane_id="%5")
            m.remember(message_id=99, pane_id="%7")
            self.assertEqual(m.lookup_pane_id(42), "%5")
            self.assertEqual(m.lookup_pane_id(99), "%7")

    def test_lookup_miss_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = MessagePaneMap(Path(tmpdir) / "map.json")
            m.remember(message_id=42, pane_id="%5")
            self.assertIsNone(m.lookup_pane_id(100))

    def test_remember_empty_pane_id_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            m = MessagePaneMap(path)
            m.remember(message_id=42, pane_id="")
            self.assertIsNone(m.lookup_pane_id(42))
            self.assertFalse(path.exists())

    def test_remember_persists_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            MessagePaneMap(path).remember(message_id=42, pane_id="%5")
            reloaded = MessagePaneMap(path)
            self.assertEqual(reloaded.lookup_pane_id(42), "%5")

    def test_corrupted_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text("{not-json", encoding="utf-8")
            m = MessagePaneMap(path)
            self.assertIsNone(m.lookup_pane_id(42))

    def test_enforce_cap_evicts_oldest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            m = MessagePaneMap(path)
            m.MAX_ENTRIES = 3
            m.remember(message_id=1, pane_id="%1")
            m.remember(message_id=2, pane_id="%2")
            m.remember(message_id=3, pane_id="%3")
            m.remember(message_id=4, pane_id="%4")
            self.assertIsNone(m.lookup_pane_id(1))
            self.assertEqual(m.lookup_pane_id(2), "%2")
            self.assertEqual(m.lookup_pane_id(4), "%4")

    def test_evict_expired_drops_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            m = MessagePaneMap(path)
            m.TTL_SECONDS = 0.01
            m.remember(message_id=1, pane_id="%1")
            import time as _time
            _time.sleep(0.05)
            m.remember(message_id=2, pane_id="%2")
            self.assertIsNone(m.lookup_pane_id(1))
            self.assertEqual(m.lookup_pane_id(2), "%2")


class TelegramReplyRoutingTests(unittest.TestCase):
    def test_process_update_reply_routes_to_mapped_pane(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = MessagePaneMap(Path(tmpdir) / "map.json")
            m.remember(message_id=500, pane_id="%15")
            router = FakeRouter()
            listener = TelegramListener(
                client=mock.Mock(),
                router=router,
                message_pane_map=m,
            )
            listener.client.send_message = mock.Mock()
            listener.process_update(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 600,
                        "chat": {"id": 1001, "type": "private"},
                        "from": {"id": 7},
                        "text": "reply to agent",
                        "reply_to_message": {
                            "message_id": 500,
                            "chat": {"id": 1001},
                            "from": {"id": 1234567},
                            "text": "agent reply",
                        },
                    },
                }
            )
            self.assertEqual(router.calls[-1]["pane_id"], "%15")

    def test_process_update_reply_miss_falls_back_to_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = MessagePaneMap(Path(tmpdir) / "map.json")
            router = FakeRouter()
            listener = TelegramListener(
                client=mock.Mock(),
                router=router,
                message_pane_map=m,
            )
            listener.client.send_message = mock.Mock()
            listener.process_update(
                {
                    "update_id": 2,
                    "message": {
                        "message_id": 601,
                        "chat": {"id": 1001, "type": "private"},
                        "from": {"id": 7},
                        "text": "reply to unknown",
                        "reply_to_message": {
                            "message_id": 999,
                            "chat": {"id": 1001},
                            "from": {"id": 1234567},
                            "text": "old message",
                        },
                    },
                }
            )
            self.assertIsNone(router.calls[-1]["pane_id"])

    def test_process_update_non_reply_pane_id_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = MessagePaneMap(Path(tmpdir) / "map.json")
            m.remember(message_id=500, pane_id="%15")
            router = FakeRouter()
            listener = TelegramListener(
                client=mock.Mock(),
                router=router,
                message_pane_map=m,
            )
            listener.client.send_message = mock.Mock()
            listener.process_update(
                {
                    "update_id": 3,
                    "message": {
                        "message_id": 602,
                        "chat": {"id": 1001, "type": "private"},
                        "from": {"id": 7},
                        "text": "plain message",
                    },
                }
            )
            self.assertIsNone(router.calls[-1]["pane_id"])

    def test_process_update_reply_without_map_falls_back(self) -> None:
        router = FakeRouter()
        listener = TelegramListener(
            client=mock.Mock(),
            router=router,
        )
        listener.client.send_message = mock.Mock()
        listener.process_update(
            {
                "update_id": 4,
                "message": {
                    "message_id": 603,
                    "chat": {"id": 1001, "type": "private"},
                    "from": {"id": 7},
                    "text": "reply but no map",
                    "reply_to_message": {
                        "message_id": 500,
                        "chat": {"id": 1001},
                        "from": {"id": 1234567},
                        "text": "agent reply",
                    },
                },
            }
        )
        self.assertIsNone(router.calls[-1]["pane_id"])

    def test_process_update_reply_malformed_message_id_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            m = MessagePaneMap(Path(tmpdir) / "map.json")
            m.remember(message_id=500, pane_id="%15")
            router = FakeRouter()
            listener = TelegramListener(
                client=mock.Mock(),
                router=router,
                message_pane_map=m,
            )
            listener.client.send_message = mock.Mock()
            listener.process_update(
                {
                    "update_id": 5,
                    "message": {
                        "message_id": 604,
                        "chat": {"id": 1001, "type": "private"},
                        "from": {"id": 7},
                        "text": "reply with bad id",
                        "reply_to_message": {
                            "chat": {"id": 1001},
                            "from": {"id": 1234567},
                        },
                    },
                }
            )
            self.assertIsNone(router.calls[-1]["pane_id"])


class ReplyBridgeMessagePaneMapPathTests(unittest.TestCase):
    def test_default_message_pane_map_path_matches_facade(self) -> None:
        bridge = load_reply_bridge()
        self.assertEqual(bridge.DEFAULT_MESSAGE_PANE_MAP_PATH, default_message_pane_map_path())

    def test_send_reply_records_message_id_to_pane_id(self) -> None:
        bridge = load_reply_bridge()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps({"allowed_user_ids": [7]}),
                encoding="utf-8",
            )
            secret_env_path = Path(tmpdir) / "telegram.env"
            secret_env_path.write_text("PSC_TELEGRAM_BOT_TOKEN=fake-token\n", encoding="utf-8")
            bindings_path = Path(tmpdir) / "bindings.json"
            bindings_path.write_text(json.dumps({"7": 1001}), encoding="utf-8")
            map_path = Path(tmpdir) / "map.json"
            opener = FakeOpener([{"ok": True, "result": {"message_id": 42}}])

            bridge.send_reply(
                text="agent reply",
                source_user_id=7,
                config_path=config_path,
                secret_env_path=secret_env_path,
                bindings_path=bindings_path,
                message_pane_map_path=map_path,
                pane_id="%5",
                opener=opener,
            )

            m = bridge.MessagePaneMap(map_path)
            self.assertEqual(m.lookup_pane_id(42), "%5")

    def test_send_reply_without_pane_id_skips_recording(self) -> None:
        bridge = load_reply_bridge()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps({"allowed_user_ids": [7]}),
                encoding="utf-8",
            )
            secret_env_path = Path(tmpdir) / "telegram.env"
            secret_env_path.write_text("PSC_TELEGRAM_BOT_TOKEN=fake-token\n", encoding="utf-8")
            bindings_path = Path(tmpdir) / "bindings.json"
            bindings_path.write_text(json.dumps({"7": 1001}), encoding="utf-8")
            map_path = Path(tmpdir) / "map.json"
            opener = FakeOpener([{"ok": True, "result": {"message_id": 42}}])

            bridge.send_reply(
                text="agent reply",
                source_user_id=7,
                config_path=config_path,
                secret_env_path=secret_env_path,
                bindings_path=bindings_path,
                message_pane_map_path=map_path,
                pane_id=None,
                env={"TMUX_PANE": "", "PSC_TELEGRAM_BOT_TOKEN": "fake-token"},
                opener=opener,
            )

            self.assertFalse(map_path.exists())
