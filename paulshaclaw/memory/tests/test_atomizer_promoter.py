from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import promoter
from paulshaclaw.memory.atomizer.config import AtomizerConfig
from paulshaclaw.memory.atomizer.splitter import Fragment

CFG = AtomizerConfig(schema_version="1", boundary_patterns=(r"^#{1,6}\s",), max_fragment_chars=8000,
                     artifact_kind_map={"research": "research"}, phase_map={"research": "research"},
                     default_artifact_kind="report", default_phase="review")


def _frag():
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact="research", captured_at="2026-05-31T00:00:00Z",
                    provenance={"repo": "r", "commit": "c", "path": "p"}, fragment_index=0, body="alpha")


class PromoterTests(unittest.TestCase):
    def test_identity_promoter_is_one_to_one(self):
        slices = promoter.IdentityPromoter().promote(_frag(), CFG)
        self.assertEqual(len(slices), 1)

    def test_slice_carries_derivation(self):
        s = promoter.IdentityPromoter().promote(_frag(), CFG)[0]
        self.assertEqual(s.frontmatter["distilled_from"], "claude:s1")
        self.assertEqual(s.frontmatter["fragment_ref"], "claude__s1__000")


if __name__ == "__main__":
    unittest.main()
