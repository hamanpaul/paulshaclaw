#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

# 本檔是刻意設計的 standalone 工具（安裝到 ~/.agents/skills/bro/scripts/ 後
# 由 hook 以絕對路徑呼叫，執行時不在 repo 裡、沒有 repo venv，故不可
# `import paulshaclaw.*`），因此下列四個預設值無法直接引用
# paulshaclaw/config/paths.py 這個 facade，只能維持字面常數。
# 對應的單一事實來源是 paulshaclaw/bot/reply.py 的
# default_config_path() / default_secret_env_path() / default_bindings_path()
# / default_message_pane_map_path()（皆透過 facade 組出相同路徑）；兩邊是否
# 仍一致由 custom-skills/bro/tests/test_reply_bridge.py 的
# test_default_paths_match_facade 於 CI 把關（issue #90：先前無此把關，
# 路徑漂移只能肉眼發現）。改這裡的字面路徑時務必同步確認該測試仍綠燈。
DEFAULT_CONFIG_PATH = Path.home() / ".config/paulshaclaw/paulshaclaw.state.json"
DEFAULT_SECRET_ENV_PATH = Path.home() / ".config/paulshaclaw/paulshaclaw.telegram.secret.env"
DEFAULT_BINDINGS_PATH = Path.home() / ".agents/state/telegram-chat-bindings.json"
DEFAULT_MESSAGE_PANE_MAP_PATH = Path.home() / ".agents/state/telegram-message-pane-map.json"

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
            # No newline within the window: hard split, drop nothing.
            chunks.append(remaining[:limit])
            remaining = remaining[limit:]
        else:
            # Split on the newline; consume only that single delimiter newline,
            # preserving any further blank lines in the next chunk.
            chunks.append(remaining[:cut])
            remaining = remaining[cut + 1:]
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

    def send_message(self, *, chat_id: int, text: str) -> int | None:
        result = self._post("sendMessage", {"chat_id": chat_id, "text": text})
        if isinstance(result, dict):
            message_id = result.get("message_id")
            if isinstance(message_id, int):
                return message_id
        return None

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
    parser.add_argument("--message-pane-map-path", help="message_id→pane_id map JSON path")
    parser.add_argument("--api-base", default="https://api.telegram.org", help="Telegram API base URL")
    parser.add_argument("--dry-run", action="store_true", help="Resolve targets and echo the text without sending to Telegram")
    return parser


class MessagePaneMap:
    """message_id → pane_id 對應表（#34），standalone 副本。

    與 paulshaclaw/bot/reply.py 的 MessagePaneMap 邏輯一致——刻意不 import
    repo 套件（見檔頭註解）；兩邊的預設路徑是否一致由
    custom-skills/bro/tests/test_reply_bridge.py 的 test_default_paths_match_facade 把關。
    """

    MAX_ENTRIES = 500
    TTL_SECONDS = 7 * 24 * 3600

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def remember(self, *, message_id: int, pane_id: str) -> None:
        if not pane_id:
            return
        with self._locked():
            payload = self._load()
            payload[str(int(message_id))] = {"pane_id": pane_id, "ts": time.time()}
            self._evict_expired(payload)
            self._enforce_cap(payload)
            self._write(payload)

    def lookup_pane_id(self, message_id: int) -> str | None:
        with self._locked():
            payload = self._load()
            entry = payload.get(str(int(message_id)))
            if not isinstance(entry, dict):
                return None
            pane_id = entry.get("pane_id")
            if isinstance(pane_id, str) and pane_id:
                return pane_id
            return None

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        lock_path = self.path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _write(self, payload: dict[str, dict[str, object]]) -> None:
        if not payload:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 原子寫入：同目錄暫存檔 + os.replace。直接 write_text 若中途中斷會留下
        # 半截 JSON，而 `_load()` 把 decode 失敗當空表——那等於靜默丟掉整份對應。
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self.path)

    def _evict_expired(self, payload: dict[str, dict[str, object]]) -> None:
        cutoff = time.time() - self.TTL_SECONDS
        expired = [
            key
            for key, entry in payload.items()
            if isinstance(entry, dict)
            and isinstance(entry.get("ts"), (int, float))
            and entry["ts"] < cutoff
        ]
        for key in expired:
            del payload[key]

    def _enforce_cap(self, payload: dict[str, dict[str, object]]) -> None:
        if len(payload) <= self.MAX_ENTRIES:
            return
        sorted_items = sorted(
            payload.items(),
            key=lambda item: item[1].get("ts", 0) if isinstance(item[1], dict) else 0,
        )
        for key, _ in sorted_items[: len(payload) - self.MAX_ENTRIES]:
            del payload[key]


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
    message_pane_map_path: str | Path | None = None,
    pane_id: str | None = None,
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

    resolved_pane_id = pane_id if pane_id is not None else (reply_env.get("TMUX_PANE", "") or "").strip() or None
    resolved_map_path = message_pane_map_path or reply_env.get("PSC_MESSAGE_PANE_MAP_PATH") or DEFAULT_MESSAGE_PANE_MAP_PATH
    message_pane_map = MessagePaneMap(resolved_map_path) if resolved_pane_id else None

    token = reply_env.get("PSC_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("PSC_TELEGRAM_BOT_TOKEN 未設定")
    client = TelegramApiClient(token, opener=opener, api_base=api_base)
    for target in targets:
        for chunk in _chunk_text(text):
            message_id = client.send_message(chat_id=target.chat_id, text=chunk)
            if message_pane_map is not None and message_id is not None:
                try:
                    message_pane_map.remember(message_id=message_id, pane_id=resolved_pane_id)
                except (OSError, ValueError):
                    pass
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
            message_pane_map_path=args.message_pane_map_path,
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
