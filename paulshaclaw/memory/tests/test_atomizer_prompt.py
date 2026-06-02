from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import prompt as prompt_mod
from paulshaclaw.memory.atomizer.splitter import Fragment


def _frag(index, body):
    return Fragment(
        project="paulshaclaw",
        source_agent="claude",
        source_session="s1",
        source_artifact="research",
        captured_at="2026-06-02T00:00:00Z",
        provenance={"repo": "r", "commit": "c", "path": "p"},
        fragment_index=index,
        body=body,
    )


class PromptTests(unittest.TestCase):
    def test_includes_skill_fragments_projects_and_json_only_instruction(self):
        text = prompt_mod.build_prompt(
            "SKILLDOC",
            [_frag(0, "alpha"), _frag(1, "beta")],
            ["paulshaclaw", "prplos-core"],
        )
        self.assertIn("SKILLDOC", text)
        self.assertIn("alpha", text)
        self.assertIn("beta", text)
        self.assertIn("prplos-core", text)
        self.assertIn("paulshaclaw", text)
        self.assertIn("[fragment 0]", text)
        self.assertIn("[fragment 1]", text)
        self.assertIn("captured_at: 2026-06-02T00:00:00Z", text)
        self.assertIn("provenance.repo: r", text)
        self.assertIn("provenance.commit: c", text)
        self.assertIn("provenance.path: p", text)
        self.assertIn("Return ONLY the JSON array", text)

    def test_deterministic(self):
        frags = [_frag(0, "alpha")]
        self.assertEqual(
            prompt_mod.build_prompt("S", frags, ["p"]),
            prompt_mod.build_prompt("S", frags, ["p"]),
        )


if __name__ == "__main__":
    unittest.main()
