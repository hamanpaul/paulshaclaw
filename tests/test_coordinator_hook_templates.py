from __future__ import annotations

import json
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "scripts" / "coordinator" / "hooks"


class HookTemplateSchemaTests(unittest.TestCase):
    """smoke 實證的 schema：copilot 用 `bash` 鍵；codex 用 CamelCase 巢狀 + matcher。"""

    def test_copilot_uses_bash_key_not_command(self) -> None:
        d = json.loads((HOOKS / "copilot.json").read_text(encoding="utf-8"))
        self.assertEqual(d.get("version"), 1)
        for ev in ("sessionStart", "agentStop"):
            self.assertIn(ev, d["hooks"])
            for entry in d["hooks"][ev]:
                self.assertIn("bash", entry)        # copilot hook 用 bash 鍵
                self.assertNotIn("command", entry)  # 非 command

    def test_codex_uses_camelcase_nested_with_matcher(self) -> None:
        d = json.loads((HOOKS / "codex.json").read_text(encoding="utf-8"))
        self.assertIn("SessionStart", d["hooks"])   # CamelCase
        self.assertIn("Stop", d["hooks"])
        self.assertNotIn("session_start", d["hooks"])  # 非 snake_case
        self.assertNotIn("stop", d["hooks"])
        for ev in ("SessionStart", "Stop"):
            grp = d["hooks"][ev][0]
            self.assertIn("hooks", grp)              # 巢狀 hooks 陣列
            self.assertIn("matcher", grp)
            self.assertIn("command", grp["hooks"][0])

    def test_relay_path_resolvable_via_repo_root_env(self) -> None:
        # 相對路徑在 cwd≠repo 時不可解；範本改用 ${PSC_REPO_ROOT}（launcher 注入）。
        for f in ("copilot.json", "codex.json"):
            self.assertIn("PSC_REPO_ROOT", (HOOKS / f).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
