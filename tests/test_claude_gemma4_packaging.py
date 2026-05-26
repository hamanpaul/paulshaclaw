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
    "model": "gemma4-31b-mtp",
    "skipDangerousModePermissionPrompt": True,
    "theme": "dark",
    "effortLevel": "low",
}


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
        self.assertIn(
            'GEMMA_PROXY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/claude-gemma4-proxy"',
            script_text,
        )
        self.assertIn('"effortLevel": "max"', script_text)
        self.assertNotIn("GEMMA_SETTINGS_TEMPLATE=", script_text)
        self.assertNotIn('cp "$GEMMA_SETTINGS_TEMPLATE" "$GEMMA_SETTINGS"', script_text)

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

    def test_proxy_send_does_not_forward_duplicate_content_length_header(self) -> None:
        module = load_proxy_module()
        handler = ProxyHandlerHarness()

        module.ProxyHandler._send(handler, 200, b"ok", {"Content-Length": "999", "X-Test": "1"})

        self.assertEqual(handler.sent_headers.count(("Content-Length", "999")), 0)
        self.assertEqual(handler.sent_headers.count(("Content-Length", "2")), 1)


if __name__ == "__main__":
    unittest.main()
