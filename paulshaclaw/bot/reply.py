from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from paulshaclaw.bot.listener import TelegramApiClient, TelegramApiError, load_bot_settings
from paulshaclaw.core.config import load_config

DEFAULT_CONFIG_PATH = Path.home() / ".config/paulshaclaw/paulshaclaw.state.json"
DEFAULT_SECRET_ENV_PATH = Path.home() / ".config/paulshaclaw/paulshaclaw.telegram.secret.env"
DEFAULT_BINDINGS_PATH = Path.home() / ".agents/state/telegram-chat-bindings.json"


@dataclass(frozen=True)
class ReplyTarget:
    user_id: int
    chat_id: int


class TelegramChatBindingStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def remember(self, *, user_id: int, chat_id: int) -> None:
        payload = self._load()
        payload[str(int(user_id))] = int(chat_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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


class TelegramReplyBridge:
    def __init__(
        self,
        *,
        client: TelegramApiClient,
        bindings: TelegramChatBindingStore,
        allowed_user_ids: Sequence[int],
    ) -> None:
        self.client = client
        self.bindings = bindings
        self.allowed_user_ids = tuple(int(value) for value in allowed_user_ids)

    def reply(self, *, text: str, source_user_id: int | None) -> list[ReplyTarget]:
        if not text.strip():
            raise ValueError("reply text 不可為空")
        targets = self.bindings.resolve_targets(
            allowed_user_ids=self.allowed_user_ids,
            source_user_id=source_user_id,
        )
        for target in targets:
            self.client.send_message(chat_id=target.chat_id, text=text)
        return targets


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


def build_reply_bridge(
    *,
    config_path: str | Path | None = None,
    secret_env_path: str | Path | None = None,
    bindings_path: str | Path | None = None,
    opener=None,
    env: Mapping[str, str] | None = None,
) -> TelegramReplyBridge:
    reply_env = load_reply_env(secret_env_path=secret_env_path, env=env)
    if config_path is None and "PSC_STAGE1_CONFIG" not in reply_env and DEFAULT_CONFIG_PATH.exists():
        reply_env = dict(reply_env)
        reply_env["PSC_STAGE1_CONFIG"] = str(DEFAULT_CONFIG_PATH)

    settings = load_bot_settings(reply_env)
    config = load_config(config_path=config_path, env=reply_env)
    bindings = TelegramChatBindingStore(bindings_path or reply_env.get("PSC_TELEGRAM_BINDINGS_PATH") or DEFAULT_BINDINGS_PATH)
    return TelegramReplyBridge(
        client=TelegramApiClient(settings.token, opener=opener),
        bindings=bindings,
        allowed_user_ids=config.allowed_user_ids,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a PaulShiaBro Telegram reply to bound operator chats")
    parser.add_argument("--text", required=True, help="Reply text to send via Telegram")
    parser.add_argument("--source-user-id", type=int, help="Reply only to the source user's bound Telegram chat")
    parser.add_argument("--config", help="Stage 1 JSON config path; defaults to PSC_STAGE1_CONFIG or ~/.config/paulshaclaw/paulshaclaw.state.json")
    parser.add_argument("--secret-env", help="Telegram secret env path; defaults to PSC_TELEGRAM_SECRET_ENV or ~/.config/paulshaclaw/paulshaclaw.telegram.secret.env")
    parser.add_argument("--bindings-path", help="Telegram chat bindings JSON path; defaults to PSC_TELEGRAM_BINDINGS_PATH or ~/.agents/state/telegram-chat-bindings.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        bridge = build_reply_bridge(
            config_path=args.config,
            secret_env_path=args.secret_env,
            bindings_path=args.bindings_path,
        )
        targets = bridge.reply(text=args.text, source_user_id=args.source_user_id)
        print(_format_delivery_summary(targets), flush=True)
        print(args.text, flush=True)
    except (FileNotFoundError, ValueError, TelegramApiError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1
    return 0


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


def _default_secret_env_path(env: Mapping[str, str]) -> Path | None:
    raw_path = env.get("PSC_TELEGRAM_SECRET_ENV", "").strip()
    if raw_path:
        return Path(raw_path)
    if DEFAULT_SECRET_ENV_PATH.exists():
        return DEFAULT_SECRET_ENV_PATH
    return None


def _format_delivery_summary(targets: Sequence[ReplyTarget]) -> str:
    return "\n".join(f"已送出到 user={target.user_id} chat={target.chat_id}" for target in targets)


if __name__ == "__main__":
    raise SystemExit(main())
