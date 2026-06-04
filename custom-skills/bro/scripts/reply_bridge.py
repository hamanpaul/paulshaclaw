#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

DEFAULT_CONFIG_PATH = Path.home() / ".config/paulshaclaw/paulshaclaw.state.json"
DEFAULT_SECRET_ENV_PATH = Path.home() / ".config/paulshaclaw/paulshaclaw.telegram.secret.env"
DEFAULT_BINDINGS_PATH = Path.home() / ".agents/state/telegram-chat-bindings.json"

TELEGRAM_TEXT_LIMIT = 4000

OpenUrl = Callable[[urllib.request.Request, float], Any]


def _chunk_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split text into <=limit pieces, preferring newline boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


@dataclass(frozen=True)
class ReplyTarget:
    user_id: int
    chat_id: int


class TelegramApiError(RuntimeError):
    """Raised when Telegram Bot API rejects a request or returns invalid data."""


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


class TelegramChatBindingStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def lookup_chat_id(self, user_id: int) -> int | None:
        payload = self._load()
        raw_value = payload.get(str(int(user_id)))
        if raw_value is None:
            return None
        return int(raw_value)

    def resolve_targets(self, *, allowed_user_ids: Sequence[int], source_user_id: int | None) -> list[ReplyTarget]:
        if source_user_id is not None:
            if source_user_id not in allowed_user_ids:
                raise ValueError(f"source user {source_user_id} 未授權")
            chat_id = self.lookup_chat_id(source_user_id)
            if chat_id is None:
                raise ValueError(f"找不到 source user {source_user_id} 對應的 Telegram chat 綁定")
            return [ReplyTarget(user_id=source_user_id, chat_id=chat_id)]

        targets: list[ReplyTarget] = []
        for user_id in allowed_user_ids:
            chat_id = self.lookup_chat_id(user_id)
            if chat_id is None:
                continue
            targets.append(ReplyTarget(user_id=user_id, chat_id=chat_id))
        if not targets:
            raise ValueError("找不到任何 allow user 的 Telegram chat 綁定")
        return targets

    def _load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Telegram chat bindings 格式錯誤: {self.path}")
        resolved: dict[str, int] = {}
        for key, value in payload.items():
            resolved[str(int(key))] = int(value)
        return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a PaulShiaBro Telegram reply without relying on the current workspace")
    parser.add_argument("--text", required=True, help="Reply text to send via Telegram")
    parser.add_argument("--source-user-id", type=int, help="Reply only to the source user's bound Telegram chat")
    parser.add_argument("--config", help="Stage 1 JSON config path")
    parser.add_argument("--secret-env", help="Telegram secret env path")
    parser.add_argument("--bindings-path", help="Telegram chat bindings JSON path")
    parser.add_argument("--api-base", default="https://api.telegram.org", help="Telegram API base URL")
    parser.add_argument("--dry-run", action="store_true", help="Resolve targets and echo the text without sending to Telegram")
    return parser


def load_reply_env(
    *,
    secret_env_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    resolved_env = dict(os.environ if env is None else env)
    resolved_path = Path(secret_env_path) if secret_env_path is not None else _default_secret_env_path(resolved_env)
    if resolved_path is None:
        return resolved_env
    if not resolved_path.exists():
        if "PSC_TELEGRAM_BOT_TOKEN" in resolved_env:
            return resolved_env
        raise FileNotFoundError(f"找不到 Telegram secret env: {resolved_path}")

    payload = _parse_env_file(resolved_path)
    payload.update(resolved_env)
    return payload


def load_allowed_user_ids(
    *,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[int, ...]:
    resolved_env = os.environ if env is None else env
    path = _default_config_path(config_path=config_path, env=resolved_env)
    if not path.exists():
        raise FileNotFoundError(f"找不到 PaulShiaBro config: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("設定檔格式錯誤")
    raw_allowed = payload.get("allowed_user_ids", [])
    if not isinstance(raw_allowed, list):
        raise ValueError("config.allowed_user_ids 格式錯誤")
    return tuple(int(value) for value in raw_allowed)


def resolve_reply_targets(
    *,
    source_user_id: int | None,
    config_path: str | Path | None = None,
    secret_env_path: str | Path | None = None,
    bindings_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], list[ReplyTarget]]:
    reply_env = load_reply_env(secret_env_path=secret_env_path, env=env)
    allowed_user_ids = load_allowed_user_ids(config_path=config_path, env=reply_env)
    bindings = TelegramChatBindingStore(bindings_path or reply_env.get("PSC_TELEGRAM_BINDINGS_PATH") or DEFAULT_BINDINGS_PATH)
    targets = bindings.resolve_targets(allowed_user_ids=allowed_user_ids, source_user_id=source_user_id)
    return reply_env, targets


def send_reply(
    *,
    text: str,
    source_user_id: int | None,
    config_path: str | Path | None = None,
    secret_env_path: str | Path | None = None,
    bindings_path: str | Path | None = None,
    api_base: str = "https://api.telegram.org",
    env: Mapping[str, str] | None = None,
    opener: OpenUrl | None = None,
    dry_run: bool = False,
) -> list[ReplyTarget]:
    if not text.strip():
        raise ValueError("reply text 不可為空")
    reply_env, targets = resolve_reply_targets(
        source_user_id=source_user_id,
        config_path=config_path,
        secret_env_path=secret_env_path,
        bindings_path=bindings_path,
        env=env,
    )
    if dry_run:
        return targets

    token = reply_env.get("PSC_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("PSC_TELEGRAM_BOT_TOKEN 未設定")
    client = TelegramApiClient(token, opener=opener, api_base=api_base)
    for target in targets:
        for chunk in _chunk_text(text):
            client.send_message(chat_id=target.chat_id, text=chunk)
    return targets


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        targets = send_reply(
            text=args.text,
            source_user_id=args.source_user_id,
            config_path=args.config,
            secret_env_path=args.secret_env,
            bindings_path=args.bindings_path,
            api_base=args.api_base,
            dry_run=args.dry_run,
        )
        print(_format_delivery_summary(targets, dry_run=args.dry_run), flush=True)
        print(args.text, flush=True)
    except (FileNotFoundError, ValueError, TelegramApiError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1
    return 0


def _default_config_path(*, config_path: str | Path | None, env: Mapping[str, str]) -> Path:
    if config_path is not None:
        return Path(config_path)
    raw_env_path = env.get("PSC_STAGE1_CONFIG", "").strip()
    if raw_env_path:
        return Path(raw_env_path)
    return DEFAULT_CONFIG_PATH


def _default_secret_env_path(env: Mapping[str, str]) -> Path | None:
    raw_path = env.get("PSC_TELEGRAM_SECRET_ENV", "").strip()
    if raw_path:
        return Path(raw_path)
    if DEFAULT_SECRET_ENV_PATH.exists():
        return DEFAULT_SECRET_ENV_PATH
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Telegram secret env 格式錯誤: {path}")
        payload[key.strip()] = value.strip()
    return payload


def _format_delivery_summary(targets: Sequence[ReplyTarget], *, dry_run: bool) -> str:
    prefix = "將送出到" if dry_run else "已送出到"
    return "\n".join(f"{prefix} user={target.user_id} chat={target.chat_id}" for target in targets)


if __name__ == "__main__":
    raise SystemExit(main())
