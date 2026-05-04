from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from paulshaclaw.bot.telegram import TelegramCommandRouter
from paulshaclaw.core.config import AppConfig, load_config
from paulshaclaw.core.daemon import PaulShiaBroDaemon


OpenUrl = Callable[[urllib.request.Request, float], Any]


class TelegramApiError(RuntimeError):
    """Raised when Telegram Bot API rejects a request or returns invalid data."""


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


def build_dispatch_guard_daemon(config: AppConfig) -> PaulShiaBroDaemon:
    return PaulShiaBroDaemon(config=config, coordinator=UnavailableCoordinator())


class TelegramListener:
    def __init__(
        self,
        *,
        client: TelegramApiClient,
        router: TelegramCommandRouter,
        poll_timeout: int = 30,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.router = router
        self.poll_timeout = poll_timeout
        self.sleep = sleep
        self.offset: int | None = None
        self.max_backoff = 30.0

    def drain_pending(self) -> None:
        updates = self.client.get_updates(offset=self.offset, timeout=0)
        for update in updates:
            next_offset = self._next_offset(update)
            if next_offset is not None:
                self.offset = next_offset

    def run_once(self) -> None:
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

        text = message.get("text")
        if not isinstance(text, str):
            return

        result = self.router.handle_message(user_id=user_id, text=text)
        self._safe_send(chat_id=chat_id, text=str(result["message"]))

    def _safe_send(self, *, chat_id: int, text: str) -> None:
        try:
            self.client.send_message(chat_id=chat_id, text=text)
        except TelegramApiError as error:
            print(f"Telegram sendMessage error: {error}", file=sys.stderr)

    def _next_offset(self, update: Mapping[str, object]) -> int | None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            return update_id + 1
        return None


def build_listener(
    *,
    config_path: str | None,
    settings: BotSettings,
    client: TelegramApiClient | None = None,
    poll_timeout: int = 30,
) -> TelegramListener:
    config = load_config(config_path=config_path)
    daemon = build_dispatch_guard_daemon(config)
    router = TelegramCommandRouter(daemon=daemon)
    return TelegramListener(
        client=client or TelegramApiClient(settings.token),
        router=router,
        poll_timeout=poll_timeout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaulShiaBro Telegram listener")
    parser.add_argument("--config", help="Stage 1 JSON 設定檔路徑")
    parser.add_argument("--poll-timeout", type=int, default=30)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_bot_settings()
        client = TelegramApiClient(settings.token)
        validate_bot_identity(client, settings)
        listener = build_listener(
            config_path=args.config,
            settings=settings,
            client=client,
            poll_timeout=args.poll_timeout,
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
