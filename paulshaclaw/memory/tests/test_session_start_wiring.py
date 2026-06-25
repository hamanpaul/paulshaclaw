"""Tests that each SessionStart entrypoint records offered slices (#148).

The three entrypoints must call ``compute_brief_and_record`` (not the bare
``compute_brief``) so that offered slices are persisted to
``runtime/wakeup/<tool>__<sid>.json`` in production.

We mock the inner ``compute_brief`` to return a fixed brief; that lets the real
``compute_brief_and_record`` run and write the offered file.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# Entrypoint modules do ``import _bootstrap`` at module load (the hooks dir is
# normally sys.path[0] when run as a script). Make that importable here.
_HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


_BRIEF = "# wake\n- [[foo--sl-1234567890abcdef|Some Title]] — spec\n"


class SessionStartWiringTests(unittest.TestCase):
    def _run(self, module_name: str, tool: str):
        import importlib

        mod = importlib.import_module(module_name)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"session_id": "wire1", "cwd": "/x"}
            with mock.patch.dict("os.environ", {"PSC_MEMORY_ROOT": str(root)}), \
                 mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                 mock.patch(
                     "paulshaclaw.memory.hooks._wakeup_common.compute_brief",
                     return_value=_BRIEF,
                 ), \
                 mock.patch("sys.stdout", io.StringIO()):
                mod.main()
            offered = root / "runtime" / "wakeup" / f"{tool}__wire1.json"
            self.assertTrue(offered.exists(), f"{module_name} did not record offered")
            data = json.loads(offered.read_text(encoding="utf-8"))
            self.assertEqual(
                data["offered"],
                [{"id": "sl-1234567890abcdef", "title": "Some Title"}],
            )

    def test_claude_records_offered(self):
        self._run("paulshaclaw.memory.hooks.claude_session_start", "claude-code")

    def test_codex_records_offered(self):
        self._run("paulshaclaw.memory.hooks.codex_session_start", "codex")

    def test_copilot_records_offered(self):
        # copilot's TOOL constant is "copilot-cli".
        self._run("paulshaclaw.memory.hooks.copilot_session_start", "copilot-cli")


if __name__ == "__main__":
    unittest.main()
