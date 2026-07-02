"""#176 guard: 生產 dream loop（scripts/start.sh）必須傳 doc-fragment 語料 roots。

roots 集合 = instruction_corpus.default_roots()（與 #156 moc/runner 的 index 端
broad corpus 同一組來源）：index 排除什麼、產生端就擋什麼。
"""

from __future__ import annotations

import unittest
from pathlib import Path

_START_SH = Path(__file__).resolve().parents[3] / "scripts" / "start.sh"


class StartShDreamFlagsTests(unittest.TestCase):
    def _dream_cmd(self) -> str:
        text = _START_SH.read_text(encoding="utf-8")
        start = text.index("memory dream run")
        end = text.index('>>"$dream_log"', start)
        return text[start:end]

    def test_dream_run_keeps_existing_flags(self):
        cmd = self._dream_cmd()
        self.assertIn("--require-idle", cmd)
        self.assertIn("--promoter llm", cmd)

    def test_dream_run_passes_default_instruction_roots(self):
        cmd = self._dream_cmd()
        self.assertEqual(cmd.count("--instruction-root"), 9)
        for root in (
            '"$HOME/.claude/CLAUDE.md"',
            '"$HOME/CLAUDE.md"',
            '"$HOME/AGENTS.md"',
            '"$HOME/GEMINI.md"',
            '"$HOME/.codex"',
            '"$HOME/.agents"',
            '"$HOME/.gemini"',
            '"$HOME/prj_pri"',
            '"$HOME/prj_arc"',
        ):
            self.assertIn(f"--instruction-root {root}", cmd)


if __name__ == "__main__":
    unittest.main()
