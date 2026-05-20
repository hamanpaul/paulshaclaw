import json
import unittest
from pathlib import Path

from paulshaclaw.chat.backend import create_chat_backend
from paulshaclaw.chat.config import load_openai_config


class FakeResponse:
    def __init__(self, status: int, payload: bytes) -> None:
        self.status = status
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class FakeOpener:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(self, request, timeout: float):
        self.calls.append({"request": request, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response


class Stage1ChatBackendTest(unittest.TestCase):
    def make_env(self) -> dict[str, str]:
        return {
            "OPENAI_BASE_URL": "http://192.168.199.199:8000/v1/",
            "OPENAI_API_KEY": "dummy-secret",
            "OPENAI_MODEL": "gemma4-31b-mtp",
        }

    def test_load_openai_config_reads_required_env(self) -> None:
        config = load_openai_config(self.make_env())

        self.assertEqual(config.base_url, "http://192.168.199.199:8000/v1/")
        self.assertEqual(config.api_key, "dummy-secret")
        self.assertEqual(config.model, "gemma4-31b-mtp")
        self.assertEqual(config.timeout, 180.0)

    def test_load_openai_config_reads_optional_timeout_env(self) -> None:
        env = self.make_env()
        env["OPENAI_TIMEOUT_SECONDS"] = "240"

        config = load_openai_config(env)

        self.assertEqual(config.timeout, 240.0)

    def test_reply_posts_openai_compatible_chat_completion_payload(self) -> None:
        opener = FakeOpener(
            FakeResponse(200, '{"choices":[{"message":{"content":"收到"}}]}'.encode("utf-8"))
        )
        backend = create_chat_backend(env=self.make_env(), opener=opener, timeout=12.0)

        reply = backend.reply(user_id=1001, text="你好")

        self.assertEqual(reply, "收到")
        self.assertEqual(len(opener.calls), 1)
        call = opener.calls[0]
        request = call["request"]
        self.assertEqual(call["timeout"], 12.0)
        self.assertEqual(request.full_url, "http://192.168.199.199:8000/v1/chat/completions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer dummy-secret")
        self.assertEqual(request.headers["Content-type"], "application/json")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gemma4-31b-mtp")
        self.assertEqual(
            payload["messages"],
            [
                {
                    "role": "system",
                    "content": "You are PaulShiaBro, a concise assistant for the operator. Reply briefly in Traditional Chinese unless the operator asks otherwise.",
                },
                {"role": "user", "content": "你好"},
            ],
        )
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(payload["temperature"], 0.2)

    def test_missing_env_fails_closed_without_http_request(self) -> None:
        opener = FakeOpener(FakeResponse(200, b'{"choices":[{"message":{"content":"never"}}]}'))
        backend = create_chat_backend(
            env={
                "OPENAI_BASE_URL": "http://192.168.199.199:8000/v1",
                "OPENAI_API_KEY": "dummy-secret",
            },
            opener=opener,
        )

        reply = backend.reply(user_id=1001, text="你好")

        self.assertEqual(reply, "chat backend 未設定")
        self.assertEqual(opener.calls, [])

    def test_timeout_failure_is_short_and_secret_safe(self) -> None:
        opener = FakeOpener(error=TimeoutError("dummy-secret full request payload timed out"))
        backend = create_chat_backend(env=self.make_env(), opener=opener)

        reply = backend.reply(user_id=1001, text="你好")

        self.assertEqual(reply, "chat backend 逾時")
        self.assertNotIn("dummy-secret", reply)
        self.assertNotIn("payload", reply)

    def test_malformed_json_failure_is_short_and_secret_safe(self) -> None:
        opener = FakeOpener(FakeResponse(200, b'{"choices": ['))
        backend = create_chat_backend(env=self.make_env(), opener=opener)

        reply = backend.reply(user_id=1001, text="你好")

        self.assertEqual(reply, "chat backend 回應格式錯誤")
        self.assertNotIn("dummy-secret", reply)

    def test_invalid_utf8_failure_is_short_and_secret_safe(self) -> None:
        opener = FakeOpener(FakeResponse(200, b"\xff\xfe"))
        backend = create_chat_backend(env=self.make_env(), opener=opener)

        reply = backend.reply(user_id=1001, text="你好")

        self.assertEqual(reply, "chat backend 回應格式錯誤")
        self.assertNotIn("dummy-secret", reply)

    def test_non_success_response_failure_is_short_and_secret_safe(self) -> None:
        opener = FakeOpener(FakeResponse(503, b'{"error":"dummy-secret full request payload"}'))
        backend = create_chat_backend(env=self.make_env(), opener=opener)

        reply = backend.reply(user_id=1001, text="你好")

        self.assertEqual(reply, "chat backend 請求失敗")
        self.assertNotIn("dummy-secret", reply)
        self.assertNotIn("full request", reply)

    def test_global_sample_yaml_reserves_chat_provider_shape(self) -> None:
        sample = (
            Path(__file__).resolve().parents[1]
            / "paulshaclaw"
            / "config"
            / "paulshaclaw.sample.yaml"
        )
        text = sample.read_text(encoding="utf-8")

        self.assertIn("chat:", text)
        self.assertIn("provider: openai_compatible", text)
        self.assertIn("openai_compatible:", text)
        self.assertIn("timeout_seconds: 180", text)
        self.assertIn("gemini_api:", text)
        self.assertIn("copilot_oauth:", text)
        self.assertIn("enabled: false", text)


if __name__ == "__main__":
    unittest.main()
