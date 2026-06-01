from __future__ import annotations

import unittest

from paulshaclaw.lifecycle.schema import compute_checksum, parse_artifact_text, validate_frontmatter
from paulshaclaw.memory.atomizer import slice_frontmatter
from paulshaclaw.memory.atomizer.config import AtomizerConfig
from paulshaclaw.memory.atomizer.splitter import Fragment

CFG = AtomizerConfig(
    schema_version="1", boundary_patterns=(r"^#{1,6}\s",), max_fragment_chars=8000,
    artifact_kind_map={"research": "research", "session": "report"},
    phase_map={"research": "research", "report": "review"},
    default_artifact_kind="report", default_phase="review")


def _frag(source_artifact="research", index=0, body="alpha"):
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact=source_artifact, captured_at="2026-05-31T00:00:00Z",
                    provenance={"repo": "paulshaclaw", "commit": "c", "path": "docs/x.md"},
                    fragment_index=index, body=body)


class SliceFrontmatterTests(unittest.TestCase):
    def test_slice_id_deterministic(self):
        a = slice_frontmatter.build(_frag(), CFG)
        b = slice_frontmatter.build(_frag(), CFG)
        self.assertEqual(a.slice_id, b.slice_id)
        self.assertTrue(a.slice_id.startswith("sl-"))

    def test_slice_id_varies_by_fragment_index(self):
        self.assertNotEqual(slice_frontmatter.build(_frag(index=0), CFG).slice_id,
                            slice_frontmatter.build(_frag(index=1), CFG).slice_id)

    def test_artifact_kind_and_phase_mapping(self):
        s = slice_frontmatter.build(_frag(source_artifact="research"), CFG)
        self.assertEqual(s.frontmatter["artifact_kind"], "research")
        self.assertEqual(s.frontmatter["phase"], "research")

    def test_unknown_artifact_uses_defaults(self):
        s = slice_frontmatter.build(_frag(source_artifact="mystery"), CFG)
        self.assertEqual(s.frontmatter["artifact_kind"], "report")
        self.assertEqual(s.frontmatter["phase"], "review")

    def test_has_t4_contract_fields(self):
        fm = slice_frontmatter.build(_frag(), CFG).frontmatter
        for key in ("memory_layer", "source_agent", "captured_at", "provenance", "supersedes"):
            self.assertIn(key, fm)
        self.assertEqual(fm["memory_layer"], "knowledge")

    def test_checksum_matches_body(self):
        s = slice_frontmatter.build(_frag(body="hello body"), CFG)
        self.assertEqual(s.frontmatter["checksum"], compute_checksum(s.body))

    def test_passes_stage3_validation(self):
        s = slice_frontmatter.build(_frag(), CFG)
        result = validate_frontmatter(frontmatter=s.frontmatter, body=s.body)
        self.assertTrue(result.ok, result.errors)

    def test_serialized_slice_parses_and_validates(self):
        s = slice_frontmatter.build(_frag(), CFG)
        text = slice_frontmatter.render(s)
        doc = parse_artifact_text(text)
        result = validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body)
        self.assertTrue(result.ok, result.errors)

    def test_validate_reports_t4_gap(self):
        fm = {"phase": "research"}  # missing everything
        errors = slice_frontmatter.validate(fm, "body")
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
