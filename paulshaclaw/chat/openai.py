from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from paulshaclaw.chat.config import OpenAIChatConfig


class OpenAICompatibleChatBackend:
    def __init__(
        self,
        config: OpenAIChatConfig,
        opener=urllib.request.urlopen,
    ) -> None:
        self.config = config
        self.opener = opener

    def reply(self, user_id: int, text: str) -> str:
        request = self._build_request(text)
        try:
            with self.opener(request, timeout=self.config.timeout) as response:
                if not self._is_success(response):
                    return "chat backend 請求失敗"
                return self._extract_content(response.read())
        except (TimeoutError, socket.timeout):
            return "chat backend 逾時"
        except (urllib.error.URLError, OSError):
            return "chat backend 請求失敗"
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return "chat backend 回應格式錯誤"

    def _build_request(self, text: str) -> urllib.request.Request:
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": text}],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        return urllib.request.Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def _is_success(self, response) -> bool:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        return 200 <= int(status) < 300

    def _extract_content(self, raw_body: bytes) -> str:
        body = json.loads(raw_body.decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("assistant content must be a string")
        return content
