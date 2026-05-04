from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request
from unittest import mock

from paulshaclaw.bot import listener as listener_module
from paulshaclaw.bot.listener import (
    BotSettings,
    TelegramApiClient,
    TelegramApiError,
    TelegramListener,
    build_listener,
    load_bot_settings,
    load_config,
    validate_bot_identity,
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
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
        self.calls.append({"user_id": user_id, "text": text})
        return self.response


class RecordingClient:
    def __init__(self, updates: list[dict[str, object]]) -> None:
        self.updates = list(updates)
        self.sent_messages: list[dict[str, object]] = []
        self.get_updates_calls: list[dict[str, object]] = []

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
        self.get_updates_calls.append({"offset": offset, "timeout": timeout})
        return list(self.updates)

    def send_message(self, *, chat_id: int, text: str) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text})


class TelegramApiClientTests(unittest.TestCase):
    def test_get_me_posts_to_bot_endpoint(self) -> None:
        opener = FakeOpener([{"ok": True, "result": {"id": 42, "username": "psc_bot"}}])
        client = TelegramApiClient("fake-token", opener=opener)

        result = client.get_me()

        self.assertEqual(result["username"], "psc_bot")
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/getMe")
        self.assertEqual(json.loads(opener.requests[0]["data"].decode("utf-8")), {})

    def test_get_updates_sends_offset_and_timeout(self) -> None:
        opener = FakeOpener([{"ok": True, "result": [{"update_id": 11}]}])
        client = TelegramApiClient("fake-token", opener=opener)

        result = client.get_updates(offset=10, timeout=7)

        self.assertEqual(result, [{"update_id": 11}])
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/getUpdates")
        self.assertEqual(json.loads(opener.requests[0]["data"].decode("utf-8")), {"offset": 10, "timeout": 7})

    def test_get_updates_uses_poll_timeout_for_http_timeout(self) -> None:
        opener = FakeOpener([{"ok": True, "result": [{"update_id": 11}]}])
        client = TelegramApiClient("fake-token", opener=opener)

        client.get_updates(offset=10, timeout=30)

        self.assertGreater(opener.requests[0]["timeout"], 30)
        self.assertEqual(opener.requests[0]["timeout"], 35.0)

    def test_send_message_posts_chat_id_and_text(self) -> None:
        opener = FakeOpener([{"ok": True, "result": {"message_id": 7}}])
        client = TelegramApiClient("fake-token", opener=opener)

        client.send_message(chat_id=1001, text="PaulShiaBro 狀態")

        body = json.loads(opener.requests[0]["data"].decode("utf-8"))
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/sendMessage")
        self.assertEqual(body, {"chat_id": 1001, "text": "PaulShiaBro 狀態"})

    def test_set_my_commands_posts_commands_payload(self) -> None:
        opener = FakeOpener([{"ok": True, "result": True}])
        client = TelegramApiClient("fake-token", opener=opener)
        commands = [{"command": "tmate", "description": "管理 tmate remote access"}]

        client.set_my_commands(commands)

        body = json.loads(opener.requests[0]["data"].decode("utf-8"))
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/setMyCommands")
        self.assertEqual(body, {"commands": commands})

    def test_api_error_raises_without_exposing_token(self) -> None:
        opener = FakeOpener([{"ok": False, "description": "Bad Request"}])
        client = TelegramApiClient("secret-token", opener=opener)

        with self.assertRaisesRegex(TelegramApiError, "Bad Request") as raised:
            client.get_me()

        self.assertNotIn("secret-token", str(raised.exception))


class BotSettingsTests(unittest.TestCase):
    def test_load_bot_settings_requires_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "PSC_TELEGRAM_BOT_TOKEN"):
            load_bot_settings({})

    def test_load_bot_settings_parses_optional_identity(self) -> None:
        settings = load_bot_settings(
            {
                "PSC_TELEGRAM_BOT_TOKEN": "fake-token",
                "PSC_TELEGRAM_EXPECTED_USERNAME": "psc_bot",
                "PSC_TELEGRAM_EXPECTED_BOT_ID": "12345",
            }
        )

        self.assertEqual(settings.token, "fake-token")
        self.assertEqual(settings.expected_username, "psc_bot")
        self.assertEqual(settings.expected_bot_id, 12345)

    def test_validate_bot_identity_rejects_username_mismatch(self) -> None:
        opener = FakeOpener([{"ok": True, "result": {"id": 12345, "username": "other_bot"}}])
        client = TelegramApiClient("fake-token", opener=opener)
        settings = BotSettings(
            token="fake-token",
            expected_username="psc_bot",
            expected_bot_id=12345,
        )

        with self.assertRaisesRegex(ValueError, "username"):
            validate_bot_identity(client, settings, attempts=1, sleep=lambda seconds: None)


class TelegramListenerTests(unittest.TestCase):
    def test_authorized_text_routing_sends_single_reply(self) -> None:
        client = RecordingClient([])
        router = FakeRouter({"ok": True, "message": "已派工 local-1 -> task-1", "result": {"job_id": "local-1"}})
        listener = TelegramListener(client=client, router=router)

        listener.process_update(
            {
                "update_id": 1,
                "message": {
                    "chat": {"id": 1001},
                    "from": {"id": 7},
                    "text": "/status",
                },
            }
        )

        self.assertEqual(router.calls, [{"user_id": 7, "text": "/status"}])
        self.assertEqual(client.sent_messages, [{"chat_id": 1001, "text": "已派工 local-1 -> task-1"}])

    def test_unauthorized_response_is_sent_once(self) -> None:
        client = RecordingClient([])
        router = FakeRouter({"ok": False, "message": "未授權使用者"})
        listener = TelegramListener(client=client, router=router)

        listener.process_update(
            {
                "update_id": 2,
                "message": {
                    "chat": {"id": 1002},
                    "from": {"id": 99},
                    "text": "/status",
                },
            }
        )

        self.assertEqual(client.sent_messages, [{"chat_id": 1002, "text": "未授權使用者"}])

    def test_non_text_messages_are_ignored(self) -> None:
        client = RecordingClient([])
        router = FakeRouter({"ok": True, "message": "ignored"})
        listener = TelegramListener(client=client, router=router)

        listener.process_update(
            {
                "update_id": 3,
                "message": {
                    "chat": {"id": 1003},
                    "from": {"id": 7},
                },
            }
        )

        self.assertEqual(router.calls, [])
        self.assertEqual(client.sent_messages, [])

    def test_unauthorized_non_text_updates_do_not_reply(self) -> None:
        client = RecordingClient([])
        router = FakeRouter({"ok": False, "message": "未授權使用者"})
        listener = TelegramListener(client=client, router=router)

        listener.process_update(
            {
                "update_id": 4,
                "message": {
                    "chat": {"id": 1004},
                    "from": {"id": 99},
                },
            }
        )

        self.assertEqual(router.calls, [])
        self.assertEqual(client.sent_messages, [])

    def test_run_once_advances_offset_after_each_update(self) -> None:
        client = RecordingClient(
            [
                {
                    "update_id": 11,
                    "message": {
                        "chat": {"id": 1001},
                        "from": {"id": 7},
                        "text": "/status",
                    },
                }
            ]
        )
        router = FakeRouter({"ok": True, "message": "ok"})
        listener = TelegramListener(client=client, router=router)

        listener.run_once()

        self.assertEqual(client.get_updates_calls, [{"offset": None, "timeout": 30}])
        self.assertEqual(listener.offset, 12)

    def test_run_once_does_not_advance_offset_when_processing_raises(self) -> None:
        class RaisingRouter:
            def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
                raise ValueError("boom")

        client = RecordingClient(
            [
                {
                    "update_id": 11,
                    "message": {
                        "chat": {"id": 1001},
                        "from": {"id": 7},
                        "text": "/status",
                    },
                }
            ]
        )
        listener = TelegramListener(client=client, router=RaisingRouter())

        with self.assertRaisesRegex(ValueError, "boom"):
            listener.run_once()

        self.assertIsNone(listener.offset)

    def test_run_forever_backs_off_after_polling_error(self) -> None:
        class FlakyClient(RecordingClient):
            def __init__(self) -> None:
                super().__init__([])
                self.calls = 0

            def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
                self.get_updates_calls.append({"offset": offset, "timeout": timeout})
                self.calls += 1
                if self.calls == 1:
                    raise TelegramApiError("boom")
                raise KeyboardInterrupt

        sleeps: list[float] = []
        listener = TelegramListener(client=FlakyClient(), router=FakeRouter({"ok": True, "message": "ok"}), sleep=sleeps.append)

        listener.run_forever()

        self.assertEqual(sleeps, [1.0])

    def test_run_forever_caps_backoff_at_thirty_seconds(self) -> None:
        class FlakyClient(RecordingClient):
            def __init__(self) -> None:
                super().__init__([])
                self.calls = 0

            def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
                self.get_updates_calls.append({"offset": offset, "timeout": timeout})
                self.calls += 1
                if self.calls <= 7:
                    raise TelegramApiError(f"boom-{self.calls}")
                raise KeyboardInterrupt

        sleeps: list[float] = []
        listener = TelegramListener(client=FlakyClient(), router=FakeRouter({"ok": True, "message": "ok"}), sleep=sleeps.append)

        listener.run_forever()

        self.assertEqual(sleeps, [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0])


class ListenerBuildTests(unittest.TestCase):
    def test_build_dispatch_guard_daemon_installs_unavailable_coordinator(self) -> None:
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

            config = load_config(config_path=str(config_path))
            daemon = listener_module.build_dispatch_guard_daemon(config)

            self.assertIsInstance(daemon.coordinator, listener_module.UnavailableCoordinator)

    def test_build_listener_uses_unavailable_coordinator(self) -> None:
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

            listener = build_listener(
                config_path=str(config_path),
                settings=BotSettings(token="fake-token"),
                client=RecordingClient([]),
            )

            response = listener.router.handle_message(user_id=7, text="/dispatch task-1")

            self.assertFalse(response["ok"])
            self.assertIn("coordinator backend 未設定", response["message"])

    def test_dispatch_through_listener_returns_coordinator_not_configured(self) -> None:
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

            listener = build_listener(
                config_path=str(config_path),
                settings=BotSettings(token="fake-token"),
                client=RecordingClient([]),
            )
            client = listener.client
            assert isinstance(client, RecordingClient)

            listener.process_update(
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 1001},
                        "from": {"id": 7},
                        "text": "/dispatch task-1",
                    },
                }
            )

            self.assertEqual(len(client.sent_messages), 1)
            self.assertIn("coordinator backend 未設定", client.sent_messages[0]["text"])
            self.assertNotIn("local-", client.sent_messages[0]["text"])


class ListenerMainTests(unittest.TestCase):
    def test_main_success_syncs_commands_before_listener_runs(self) -> None:
        fake_listener = mock.Mock()
        fake_client = mock.Mock()
        fake_client.set_my_commands.return_value = None
        fake_commands = [{"command": "tmate", "description": "管理 tmate remote access"}]
        parent = mock.Mock()
        parent.attach_mock(fake_client, "client")
        parent.attach_mock(fake_listener, "listener")

        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")) as load_settings,
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client) as api_client,
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity") as validate_identity,
            mock.patch("paulshaclaw.bot.listener.build_listener", return_value=fake_listener) as build_listener_mock,
            mock.patch("paulshaclaw.bot.listener.load_default_command_registry") as load_registry,
        ):
            load_registry.return_value.telegram_commands.return_value = fake_commands
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 0)
        load_settings.assert_called_once_with()
        api_client.assert_called_once_with("fake-token")
        validate_identity.assert_called_once()
        fake_client.set_my_commands.assert_called_once_with(fake_commands)
        build_listener_mock.assert_called_once()
        self.assertEqual(build_listener_mock.call_args.kwargs["config_path"], None)
        self.assertEqual(build_listener_mock.call_args.kwargs["poll_timeout"], 30)
        self.assertEqual(build_listener_mock.call_args.kwargs["command_registry"], load_registry.return_value)
        self.assertLess(
            parent.mock_calls.index(mock.call.client.set_my_commands(fake_commands)),
            parent.mock_calls.index(mock.call.listener.run_forever()),
        )
        fake_listener.run_forever.assert_called_once_with()

    def test_main_returns_one_when_command_menu_sync_fails(self) -> None:
        fake_client = mock.Mock()
        fake_client.set_my_commands.side_effect = TelegramApiError("menu sync failed")

        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")),
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client),
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity"),
            mock.patch("paulshaclaw.bot.listener.load_default_command_registry") as load_registry,
        ):
            load_registry.return_value.telegram_commands.return_value = []
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 1)

    def test_main_writes_ready_file_before_run_forever(self) -> None:
        fake_listener = mock.Mock()
        fake_client = mock.Mock()
        fake_client.set_my_commands.return_value = None
        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = Path(tmpdir) / "telegram.ready"
            with (
                mock.patch.dict(os.environ, {"PSC_TELEGRAM_READY_FILE": str(ready_file)}, clear=False),
                mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")),
                mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client),
                mock.patch("paulshaclaw.bot.listener.validate_bot_identity"),
                mock.patch("paulshaclaw.bot.listener.load_default_command_registry") as load_registry,
                mock.patch("paulshaclaw.bot.listener.build_listener", return_value=fake_listener),
            ):
                load_registry.return_value.telegram_commands.return_value = []
                exit_code = listener_module.main([])
            self.assertEqual(exit_code, 0)
            self.assertEqual(ready_file.read_text(encoding="utf-8"), "ready\n")
            fake_listener.run_forever.assert_called_once_with()

    def test_main_passes_config_and_poll_timeout_to_listener_builder(self) -> None:
        fake_listener = mock.Mock()
        fake_client = mock.Mock()
        fake_client.set_my_commands.return_value = None

        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")),
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client),
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity"),
            mock.patch("paulshaclaw.bot.listener.load_default_command_registry") as load_registry,
            mock.patch("paulshaclaw.bot.listener.build_listener", return_value=fake_listener) as build_listener_mock,
        ):
            load_registry.return_value.telegram_commands.return_value = []
            exit_code = listener_module.main(["--config", "/fake/config.json", "--poll-timeout", "15"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(build_listener_mock.call_args.kwargs["config_path"], "/fake/config.json")
        self.assertEqual(build_listener_mock.call_args.kwargs["poll_timeout"], 15)

    def test_main_returns_one_when_token_missing(self) -> None:
        with mock.patch("paulshaclaw.bot.listener.load_bot_settings", side_effect=ValueError("PSC_TELEGRAM_BOT_TOKEN 未設定")):
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 1)

    def test_main_returns_one_when_config_is_bad(self) -> None:
        fake_client = mock.Mock()
        fake_client.set_my_commands.return_value = None

        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")),
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client),
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity"),
            mock.patch("paulshaclaw.bot.listener.load_default_command_registry") as load_registry,
            mock.patch("paulshaclaw.bot.listener.build_listener", side_effect=FileNotFoundError("bad config")),
        ):
            load_registry.return_value.telegram_commands.return_value = []
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 1)

    def test_main_returns_one_on_telegram_api_error(self) -> None:
        fake_client = mock.Mock()
        fake_client.set_my_commands.return_value = None
        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")),
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client),
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity", side_effect=TelegramApiError("bad bot")),
        ):
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
