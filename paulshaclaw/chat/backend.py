from __future__ import annotations

from typing import Mapping, Protocol

from paulshaclaw.chat.config import ChatConfigError, load_openai_config
from paulshaclaw.chat.openai import OpenAICompatibleChatBackend


class ChatBackend(Protocol):
    def reply(self, user_id: int, text: str) -> str:
        ...


class ClosedChatBackend:
    def reply(self, user_id: int, text: str) -> str:
        return "chat backend 未設定"


def create_chat_backend(
    *,
    env: Mapping[str, str] | None = None,
    opener=None,
    timeout: float = 180.0,
) -> ChatBackend:
    try:
        config = load_openai_config(env, timeout=timeout)
    except ChatConfigError:
        return ClosedChatBackend()

    if opener is None:
        return OpenAICompatibleChatBackend(config)
    return OpenAICompatibleChatBackend(config, opener=opener)
