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
    def test_matches_plan_prompt_sections(self):
        text = prompt_mod.build_prompt(
            "SKILLDOC",
            [_frag(0, "alpha"), _frag(1, "beta")],
            ["paulshaclaw", "prplos-core"],
        )
        self.assertEqual(
            text,
            "\n".join(
                [
                    "SKILLDOC",
                    "",
                    "## Known projects (choose exactly one per slice, or _unknown)",
                    "paulshaclaw, prplos-core",
                    "",
                    "## Session fragments to atomize",
                    "[fragment 0]",
                    "alpha",
                    "",
                    "[fragment 1]",
                    "beta",
                    "",
                    "## Output",
                    "Return ONLY the JSON array specified by the skill's output contract.",
                ]
            ),
        )

    def test_deterministic(self):
        frags = [_frag(0, "alpha")]
        self.assertEqual(
            prompt_mod.build_prompt("S", frags, ["p"]),
            prompt_mod.build_prompt("S", frags, ["p"]),
        )


if __name__ == "__main__":
    unittest.main()
