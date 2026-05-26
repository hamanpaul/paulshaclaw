from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from paulshaclaw.bot.telegram import TelegramCommandRouter
from paulshaclaw.core.config import AppConfig, load_config
from paulshaclaw.core.command_registry import CommandRegistry, load_default_command_registry
from paulshaclaw.core.daemon import PaulShiaBroDaemon
from paulshaclaw.security.ops_companion import DEFAULT_REDACTION_RULES, RedactionEngine, RedactionRule

logger = logging.getLogger(__name__)

OpenUrl = Callable[[urllib.request.Request, float], Any]
OUTBOUND_LOG_REDACTOR = RedactionEngine(
    DEFAULT_REDACTION_RULES
    + (
        RedactionRule(
            rule_id="tmate-ssh-line",
            pattern=re.compile(r"(?m)\b(ssh(?:_ro)?\s*:\s*)([^\n]+)"),
            replacement=lambda match: f"{match.group(1)}[REDACTED:TMATE_SSH]",
            classifications=("remote-access",),
        ),
        RedactionRule(
            rule_id="tmate-web-line",
            pattern=re.compile(r"(?m)\b(web(?:_ro)?\s*:\s*)([^\n]+)"),
            replacement=lambda match: f"{match.group(1)}[REDACTED:TMATE_WEB]",
            classifications=("remote-access",),
        ),
    )
)


class TelegramApiError(RuntimeError):
    """Raised when Telegram Bot API rejects a request or returns invalid data."""


class ChatBindingRecorder(Protocol):
    def remember(self, *, user_id: int, chat_id: int) -> None: ...


@dataclass(frozen=True)
class BotSettings:
    token: str
    expected_username: str | None = None
    expected_bot_id: int | None = None


class TelegramApiClient:
    def __init__(
        self,
        token: str,
        *,
        opener: OpenUrl | None = None,
        api_base: str = "https://api.telegram.org",
        timeout: float = 10.0,
    ) -> None:
        self.token = token
        self.opener = opener or urllib.request.urlopen
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def get_me(self) -> dict[str, object]:
        result = self._post("getMe", {})
        if not isinstance(result, dict):
            raise TelegramApiError("Telegram getMe returned non-object result")
        return result

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
        payload: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        result = self._post("getUpdates", payload, timeout=float(timeout) + 5.0)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getUpdates returned non-list result")
        updates: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict):
                updates.append(item)
        return updates

    def send_message(self, *, chat_id: int, text: str) -> None:
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def set_my_commands(
        self,
        commands: list[dict[str, str]],
        *,
        scope: Mapping[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"commands": commands}
        if scope is not None:
            payload["scope"] = dict(scope)
        self._post("setMyCommands", payload)

    def get_my_commands(self, *, scope: Mapping[str, object] | None = None) -> list[dict[str, object]]:
        payload: dict[str, object] = {}
        if scope is not None:
            payload["scope"] = dict(scope)
        result = self._post("getMyCommands", payload)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getMyCommands returned non-list result")
        commands: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict):
                commands.append(item)
        return commands

    def set_chat_menu_button(
        self,
        *,
        menu_button: Mapping[str, object],
        chat_id: int | None = None,
    ) -> None:
        payload: dict[str, object] = {"menu_button": dict(menu_button)}
        if chat_id is not None:
            payload["chat_id"] = chat_id
        self._post("setChatMenuButton", payload)

    def get_chat_menu_button(self, *, chat_id: int | None = None) -> dict[str, object]:
        payload: dict[str, object] = {}
        if chat_id is not None:
            payload["chat_id"] = chat_id
        result = self._post("getChatMenuButton", payload)
        if not isinstance(result, dict):
            raise TelegramApiError("Telegram getChatMenuButton returned non-object result")
        return result

    def _post(self, method: str, payload: Mapping[str, object], *, timeout: float | None = None) -> object:
        body = json.dumps(dict(payload)).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}/bot{self.token}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout if timeout is None else timeout) as response:
                raw = response.read()
        except TimeoutError as error:
            raise TelegramApiError(f"Telegram API request failed: {error}") from error
        except urllib.error.URLError as error:
            raise TelegramApiError(f"Telegram API request failed: {error.reason}") from error

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TelegramApiError("Telegram API returned invalid JSON") from error

        if not isinstance(decoded, dict):
            raise TelegramApiError("Telegram API returned non-object payload")
        if not decoded.get("ok"):
            description = str(decoded.get("description", "Telegram API request failed"))
            raise TelegramApiError(description)
        return decoded.get("result")


def load_bot_settings(env: Mapping[str, str] | None = None) -> BotSettings:
    resolved_env = os.environ if env is None else env
    token = resolved_env.get("PSC_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("PSC_TELEGRAM_BOT_TOKEN 未設定")

    expected_username = resolved_env.get("PSC_TELEGRAM_EXPECTED_USERNAME", "").strip() or None
    raw_bot_id = resolved_env.get("PSC_TELEGRAM_EXPECTED_BOT_ID", "").strip()
    expected_bot_id = int(raw_bot_id) if raw_bot_id else None
    return BotSettings(
        token=token,
        expected_username=expected_username,
        expected_bot_id=expected_bot_id,
    )


def validate_bot_identity(
    client: TelegramApiClient,
    settings: BotSettings,
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    last_error: TelegramApiError | None = None
    for attempt in range(attempts):
        try:
            identity = client.get_me()
            break
        except TelegramApiError as error:
            last_error = error
            if attempt + 1 >= attempts:
                raise
            sleep(float(attempt + 1))
    else:
        raise TelegramApiError(str(last_error))

    username = str(identity.get("username", ""))
    bot_id = int(identity.get("id", 0))
    if settings.expected_username is not None and username != settings.expected_username:
        raise ValueError(f"Telegram bot username mismatch: expected {settings.expected_username}, got {username}")
    if settings.expected_bot_id is not None and bot_id != settings.expected_bot_id:
        raise ValueError(f"Telegram bot id mismatch: expected {settings.expected_bot_id}, got {bot_id}")
    return identity


class UnavailableCoordinator:
    def create_job(self, *, phase: str, scope: str, payload: dict[str, object]) -> dict[str, object]:
        raise ValueError("coordinator backend 未設定")


def build_dispatch_guard_daemon(
    config: AppConfig,
    command_registry: CommandRegistry | None = None,
) -> PaulShiaBroDaemon:
    return PaulShiaBroDaemon(
        config=config,
        coordinator=UnavailableCoordinator(),
        command_registry=command_registry,
    )


class TelegramListener:
    def __init__(
        self,
        *,
        client: TelegramApiClient,
        router: TelegramCommandRouter,
        bindings: ChatBindingRecorder | None = None,
        command_menu: Sequence[Mapping[str, str]] | None = None,
        private_chat_ids: Sequence[int] | None = None,
        poll_timeout: int = 30,
        sleep: Callable[[float], None] = time.sleep,
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        self.client = client
        self.router = router
        self.bindings = bindings
        self.command_menu = tuple(_normalize_command_menu_entry(item) for item in (command_menu or ()))
        self.private_chat_ids = tuple(int(chat_id) for chat_id in (private_chat_ids or ()))
        self.poll_timeout = poll_timeout
        self.sleep = sleep
        self.cleanup = cleanup or (lambda: None)
        self.offset: int | None = None
        self.max_backoff = 30.0

    def drain_pending(self) -> None:
        updates = self.client.get_updates(offset=self.offset, timeout=0)
        for update in updates:
            next_offset = self._next_offset(update)
            if next_offset is not None:
                self.offset = next_offset

    def run_once(self) -> None:
        self._sync_command_menu()
        self.cleanup()
        updates = self.client.get_updates(offset=self.offset, timeout=self.poll_timeout)
        for update in updates:
            next_offset = self._next_offset(update)
            self.process_update(update)
            if next_offset is not None:
                self.offset = next_offset

    def run_forever(self) -> None:
        backoff = 1.0
        while True:
            try:
                self.run_once()
                backoff = 1.0
            except KeyboardInterrupt:
                return
            except TelegramApiError as error:
                print(f"Telegram polling error: {error}", file=sys.stderr)
                self.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    def process_update(self, update: Mapping[str, object]) -> None:
        message = update.get("message")
        if not isinstance(message, Mapping):
            return

        chat = message.get("chat")
        from_user = message.get("from")
        if not isinstance(chat, Mapping) or not isinstance(from_user, Mapping):
            return

        chat_id = chat.get("id")
        user_id = from_user.get("id")
        if not isinstance(chat_id, int) or not isinstance(user_id, int):
            return

        if (
            self.bindings is not None
            and _should_record_private_binding(chat=chat, chat_id=chat_id, user_id=user_id)
            and _is_authorized_binding_user(router=self.router, user_id=user_id)
        ):
            try:
                self.bindings.remember(user_id=user_id, chat_id=chat_id)
            except (OSError, ValueError) as error:
                logger.error("BINDING_SAVE_ERROR user=%d chat=%d error=%s", user_id, chat_id, error)

        text = message.get("text")
        if not isinstance(text, str):
            return

        logger.info("IN  user=%d chat=%d text=%r", user_id, chat_id, text)
        result = self.router.handle_message(user_id=user_id, text=text)
        reply = str(result["message"])
        self._safe_send(chat_id=chat_id, text=reply)

    def _safe_send(self, *, chat_id: int, text: str) -> None:
        logger.info("OUT chat=%d text=%r", chat_id, OUTBOUND_LOG_REDACTOR.redact(text).text)
        try:
            self.client.send_message(chat_id=chat_id, text=text)
        except TelegramApiError as error:
            logger.error("SEND_ERROR chat=%d error=%s", chat_id, error)

    def _next_offset(self, update: Mapping[str, object]) -> int | None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            return update_id + 1
        return None

    def _sync_command_menu(self) -> None:
        if not self.command_menu:
            return

        get_my_commands = getattr(self.client, "get_my_commands", None)
        set_my_commands = getattr(self.client, "set_my_commands", None)
        if not callable(get_my_commands) or not callable(set_my_commands):
            raise TypeError("Telegram client missing command menu sync methods")

        self._sync_command_scope(get_my_commands, set_my_commands, scope=None)
        self._sync_command_scope(
            get_my_commands,
            set_my_commands,
            scope={"type": "all_private_chats"},
        )
        for chat_id in self.private_chat_ids:
            self._sync_command_scope(
                get_my_commands,
                set_my_commands,
                scope={"type": "chat", "chat_id": chat_id},
            )

        get_chat_menu_button = getattr(self.client, "get_chat_menu_button", None)
        set_chat_menu_button = getattr(self.client, "set_chat_menu_button", None)
        if not callable(get_chat_menu_button) or not callable(set_chat_menu_button):
            return

        expected_menu_button = {"type": "commands"}
        for chat_id in self.private_chat_ids:
            current_menu_button = _normalize_menu_button_type(get_chat_menu_button(chat_id=chat_id))
            if current_menu_button == expected_menu_button:
                continue
            logger.info("Telegram chat menu button drift detected; syncing chat_id=%d", chat_id)
            set_chat_menu_button(chat_id=chat_id, menu_button=expected_menu_button)

    def _sync_command_scope(
        self,
        get_my_commands: Callable[..., list[dict[str, object]]],
        set_my_commands: Callable[..., None],
        *,
        scope: Mapping[str, object] | None,
    ) -> None:
        remote_items = get_my_commands() if scope is None else get_my_commands(scope=dict(scope))
        remote_commands = [
            _normalize_command_menu_entry(item)
            for item in remote_items
            if isinstance(item, Mapping)
        ]
        expected_commands = list(self.command_menu)
        if remote_commands == expected_commands:
            return

        scope_label = "default" if scope is None else str(scope.get("type", "scoped"))
        logger.info(
            "Telegram command menu drift detected; syncing %s scope with %d commands",
            scope_label,
            len(expected_commands),
        )
        if scope is None:
            set_my_commands(expected_commands)
            return
        set_my_commands(expected_commands, scope=dict(scope))


def _normalize_command_menu_entry(entry: Mapping[str, object]) -> dict[str, str]:
    command = entry.get("command")
    description = entry.get("description")
    if not isinstance(command, str) or not command:
        raise ValueError("Telegram command menu entry missing command")
    if not isinstance(description, str) or not description:
        raise ValueError("Telegram command menu entry missing description")
    return {
        "command": command,
        "description": description,
    }


def _normalize_menu_button_type(entry: Mapping[str, object]) -> dict[str, str]:
    button_type = entry.get("type")
    if not isinstance(button_type, str) or not button_type:
        raise ValueError("Telegram menu button missing type")
    return {"type": button_type}


def _should_record_private_binding(*, chat: Mapping[str, object], chat_id: int, user_id: int) -> bool:
    chat_type = chat.get("type")
    if isinstance(chat_type, str):
        return chat_type == "private"
    return chat_id > 0 and chat_id == user_id


def _is_authorized_binding_user(*, router: object, user_id: int) -> bool:
    daemon = getattr(router, "daemon", None)
    config = getattr(daemon, "config", None)
    allowed_user_ids = getattr(config, "allowed_user_ids", None)
    if isinstance(allowed_user_ids, tuple):
        return user_id in allowed_user_ids
    return True


def build_listener(
    *,
    config_path: str | None,
    settings: BotSettings,
    client: TelegramApiClient | None = None,
    poll_timeout: int = 30,
    command_registry: CommandRegistry | None = None,
) -> TelegramListener:
    from paulshaclaw.bot.reply import DEFAULT_BINDINGS_PATH, TelegramChatBindingStore

    config = load_config(config_path=config_path)
    resolved_registry = command_registry or load_default_command_registry()
    daemon = build_dispatch_guard_daemon(config, command_registry=resolved_registry)
    router = TelegramCommandRouter(daemon=daemon)
    bindings_path = os.environ.get("PSC_TELEGRAM_BINDINGS_PATH", "").strip() or str(DEFAULT_BINDINGS_PATH)
    return TelegramListener(
        client=client or TelegramApiClient(settings.token),
        router=router,
        bindings=TelegramChatBindingStore(bindings_path),
        command_menu=resolved_registry.telegram_commands(),
        private_chat_ids=config.allowed_user_ids,
        poll_timeout=poll_timeout,
        cleanup=daemon.cleanup_idle_resources,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaulShiaBro Telegram listener")
    parser.add_argument("--config", help="Stage 1 JSON 設定檔路徑")
    parser.add_argument("--poll-timeout", type=int, default=30)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_bot_settings()
        client = TelegramApiClient(settings.token)
        validate_bot_identity(client, settings)
        command_registry = load_default_command_registry()
        client.set_my_commands(command_registry.telegram_commands())
        listener = build_listener(
            config_path=args.config,
            settings=settings,
            client=client,
            poll_timeout=args.poll_timeout,
            command_registry=command_registry,
        )
        listener.drain_pending()
        ready_file = os.environ.get("PSC_TELEGRAM_READY_FILE", "").strip()
        if ready_file:
            Path(ready_file).write_text("ready\n", encoding="utf-8")
        print("Telegram listener ready", flush=True)
        listener.run_forever()
    except (ValueError, FileNotFoundError, TelegramApiError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
