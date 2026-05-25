from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_GEMMA4 = PROJECT_ROOT / "scripts" / "claude-gemma4"
CLAUDE_GEMMA4_PROXY = PROJECT_ROOT / "scripts" / "claude-gemma4-proxy"
CLAUDE_GEMMA4_SETTINGS = PROJECT_ROOT / "config" / "claude-gemma4-settings.json"


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
            {
                "permissions": {"defaultMode": "bypassPermissions"},
                "model": "gemma4-31b-mtp",
                "effortLevel": "max",
                "skipDangerousModePermissionPrompt": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
