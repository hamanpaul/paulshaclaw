from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class OpenAIChatConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 45.0
    max_tokens: int = 1024
    temperature: float = 0.2


class ChatConfigError(ValueError):
    pass


def load_openai_config(
    env: Mapping[str, str] | None = None,
    *,
    timeout: float = 45.0,
) -> OpenAIChatConfig:
    source = os.environ if env is None else env
    try:
        base_url = source["OPENAI_BASE_URL"].strip()
        api_key = source["OPENAI_API_KEY"].strip()
        model = source["OPENAI_MODEL"].strip()
    except KeyError as exc:
        raise ChatConfigError("chat backend 未設定") from exc

    if not base_url or not api_key or not model:
        raise ChatConfigError("chat backend 未設定")

    return OpenAIChatConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
