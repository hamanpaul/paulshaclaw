from __future__ import annotations

import json
import importlib.util
import io
import os
import subprocess
import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader
import urllib.error
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_GEMMA4 = PROJECT_ROOT / "scripts" / "claude-gemma4"
CLAUDE_GEMMA4_PROXY = PROJECT_ROOT / "scripts" / "claude-gemma4-proxy"
CLAUDE_GEMMA4_SETTINGS = PROJECT_ROOT / "config" / "claude-gemma4-settings.json"
EXPECTED_CLAUDE_GEMMA4_SETTINGS = {
    "permissions": {"defaultMode": "bypassPermissions"},
    "model": "gemma4-26b-a4b-nvfp4",
    "skipDangerousModePermissionPrompt": True,
    "theme": "dark",
    "effortLevel": "low",
}

EXPECTED_BOOTSTRAP_SECRET_TEMPLATE = (
    "PSC_TELEGRAM_BOT_TOKEN=replace-with-botfather-token\n"
    "PSC_TELEGRAM_EXPECTED_USERNAME=\n"
    "PSC_TELEGRAM_EXPECTED_BOT_ID=\n"
    "PSC_CLAUDE_GEMMA4_API_KEY=\n"
)


def load_proxy_module():
    loader = SourceFileLoader("claude_gemma4_proxy", str(CLAUDE_GEMMA4_PROXY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProxyHandlerHarness:
    def __init__(self) -> None:
        self.statuses: list[int] = []
        self.sent_headers: list[tuple[str, str]] = []
        self.send_calls: list[tuple[int, bytes, dict[str, str] | None]] = []
        self.body = io.BytesIO()
        self.command = "POST"
        self.path = "/v1/messages"
        self.headers_in = {
            "content-length": "2",
            "x-test": "1",
        }
        self.rfile = io.BytesIO(b"{}")
        self.wfile = io.BytesIO()

    @property
    def headers(self):  # type: ignore[override]
        return self.headers_in

    def send_response(self, status: int) -> None:
        self.statuses.append(status)

    def send_header(self, key: str, value: str) -> None:
        self.sent_headers.append((key, value))

    def end_headers(self) -> None:
        return None

    def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_calls.append((status, body, headers))


class ClaudeGemma4PackagingTests(unittest.TestCase):
    def test_claude_gemma4_script_is_packaged_with_repo_relative_proxy(self) -> None:
        self.assertTrue(CLAUDE_GEMMA4.exists(), "scripts/claude-gemma4 should exist")
        self.assertTrue(os.access(CLAUDE_GEMMA4, os.X_OK), "scripts/claude-gemma4 should be executable")
        script_text = CLAUDE_GEMMA4.read_text(encoding="utf-8")
        self.assertIn('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"', script_text)
        self.assertIn('GEMMA_PROXY="$SCRIPT_DIR/claude-gemma4-proxy"', script_text)
        self.assertIn('command -v claude', script_text)
        self.assertIn('command -v claude.exe', script_text)
        self.assertIn('${PSC_CLAUDE_GEMMA4_SECRET_ENV:-${PSC_SECRET_ENV:-$HOME/.config/paulshaclaw/paulshaclaw.telegram.secret.env}}', script_text)
        self.assertIn('${PSC_CLAUDE_GEMMA4_CONFIG_DIR:-${PSC_GEMMA4_CONFIG_DIR:-$HOME/.claude-gemma4}}', script_text)
        self.assertIn('${PSC_CLAUDE_GEMMA4_SETTINGS_TEMPLATE:-$SCRIPT_DIR/../config/claude-gemma4-settings.json}', script_text)
        self.assertIn('PSC_CLAUDE_GEMMA4_API_KEY', script_text)
        self.assertIn('OPENAI_API_KEY', script_text)
        self.assertNotIn('cat > "$GEMMA_SETTINGS" <<'"'"'"'"'"'JSON'"'"'"'"'"'', script_text)
        self.assertIn('cp "$GEMMA_SETTINGS_TEMPLATE" "$GEMMA_SETTINGS"', script_text)
        self.assertNotIn('/home/paul_chen/.nvm/versions/node', script_text)
        self.assertNotIn('/home/paul_chen/.config/paulshaclaw', script_text)
        self.assertNotIn('/home/paul_chen/.claude-gemma4', script_text)
        self.assertNotIn('"effortLevel": "max"', script_text)

    def test_proxy_script_is_packaged_and_executable(self) -> None:
        self.assertTrue(CLAUDE_GEMMA4_PROXY.exists(), "scripts/claude-gemma4-proxy should exist")
        self.assertTrue(
            os.access(CLAUDE_GEMMA4_PROXY, os.X_OK),
            "scripts/claude-gemma4-proxy should be executable",
        )

    def test_proxy_script_parses_with_py_compile(self) -> None:
        proxy_text = CLAUDE_GEMMA4_PROXY.read_text(encoding="utf-8")
        self.assertNotIn("import argparse", proxy_text)
        self.assertNotIn("parse_args(", proxy_text)
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(CLAUDE_GEMMA4_PROXY)],
            capture_output=True,
            check=False,
            cwd=PROJECT_ROOT,
            text=True,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_settings_template_matches_expected_defaults(self) -> None:
        self.assertTrue(CLAUDE_GEMMA4_SETTINGS.exists(), "config/claude-gemma4-settings.json should exist")
        self.assertEqual(
            json.loads(CLAUDE_GEMMA4_SETTINGS.read_text(encoding="utf-8")),
            EXPECTED_CLAUDE_GEMMA4_SETTINGS,
        )

    def test_proxy_forward_returns_gateway_error_on_upstream_urlerror(self) -> None:
        module = load_proxy_module()
        handler = ProxyHandlerHarness()

        with (
            mock.patch.object(module.urllib.request, "urlopen", side_effect=urllib.error.URLError("boom")),
        ):
            module.ProxyHandler._forward(handler)

        self.assertEqual(len(handler.send_calls), 1)
        self.assertEqual(handler.send_calls[0][0], 503)

    def test_proxy_uses_configurable_upstream_base_url(self) -> None:
        with mock.patch.dict(os.environ, {"PSC_CLAUDE_GEMMA4_UPSTREAM_URL": "http://example.com:9000"}):
            module = load_proxy_module()

        self.assertEqual(module.UPSTREAM, "http://example.com:9000")

    def test_proxy_hoists_system_role_messages_into_top_level_system(self) -> None:
        module = load_proxy_module()
        payload = {
            "model": "gemma4-26b-a4b-nvfp4",
            "system": "Base prompt.",
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "system", "content": [{"type": "text", "text": "Be concise."}]},
            ],
        }

        module.hoist_system_messages(payload)

        self.assertEqual([m["role"] for m in payload["messages"]], ["user"])
        self.assertIn("Base prompt.", payload["system"])
        self.assertIn("Be concise.", payload["system"])

    def test_proxy_rejects_malformed_content_length_with_bad_request(self) -> None:
        module = load_proxy_module()
        handler = ProxyHandlerHarness()
        handler.headers_in["content-length"] = "abc"

        module.ProxyHandler._forward(handler)

        self.assertEqual(handler.send_calls[0][0], 400)
        self.assertIn(b"invalid content-length", handler.send_calls[0][1])

    def test_proxy_send_does_not_forward_duplicate_content_length_header(self) -> None:
        module = load_proxy_module()
        handler = ProxyHandlerHarness()

        module.ProxyHandler._send(handler, 200, b"ok", {"Content-Length": "999", "X-Test": "1"})

        self.assertEqual(handler.sent_headers.count(("Content-Length", "999")), 0)
        self.assertEqual(handler.sent_headers.count(("Content-Length", "2")), 1)

    def test_bootstrap_secret_template_includes_dedicated_claude_api_key(self) -> None:
        template_path = PROJECT_ROOT / "paulshaclaw" / "deploy" / "templates" / "secret" / "bootstrap" / "__INSTANCE__.telegram.secret.env.tmpl"

        self.assertEqual(template_path.read_text(encoding="utf-8"), EXPECTED_BOOTSTRAP_SECRET_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
