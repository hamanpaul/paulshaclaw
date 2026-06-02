from __future__ import annotations

import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "atomizer" / "skills" / "atomize-knowledge-slice.md"


class SkillDocTests(unittest.TestCase):
    def test_skill_exists_with_frontmatter_and_output_contract(self):
        self.assertTrue(SKILL.exists(), f"missing skill doc: {SKILL}")
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), "skill doc must start with frontmatter")
        self.assertIn("\n---\n", text[4:], "skill doc must close frontmatter")
        self.assertIn("## Output contract", text)
        _, output_contract = text.split("## Output contract", maxsplit=1)
        self.assertIn("Return ONLY the JSON array.", output_contract)
        for field in (
            "title",
            "artifact_kind",
            "project",
            "tags",
            "body",
            "source_fragment_indices",
            "relations",
        ):
            self.assertIn(field, output_contract)
        for artifact_kind in (
            "research",
            "spec",
            "roadmap",
            "test",
            "task",
            "todo",
            "plan",
            "report",
            "review",
            "ship-record",
            "gate-report",
        ):
            self.assertIn(artifact_kind, output_contract)


if __name__ == "__main__":
    unittest.main()
