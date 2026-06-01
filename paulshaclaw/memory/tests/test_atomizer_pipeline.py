from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.memory.atomizer import pipeline, slice_frontmatter
from paulshaclaw.memory.atomizer.promoter import Promoter
from paulshaclaw.memory.atomizer.splitter import Fragment
from paulshaclaw.memory.ledger import processing, relations

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha body
# Topic B
beta body
"""


def _seed_raw(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(_RAW, encoding="utf-8")
    return raw


_RAW_S2 = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s2
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/y.md
---
# Topic C
gamma body
# Topic D
delta body
"""


def _seed_raw_s2(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s2.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(_RAW_S2, encoding="utf-8")
    return raw


class FailingPromoter(Promoter):
    """Promoter that makes fragment_index==1 of s1 fail validation."""
    
    def __init__(self, fail_session: str = "s1", fail_index: int = 1):
        self.fail_session = fail_session
        self.fail_index = fail_index
    
    def promote(self, fragment: Fragment, config: atomizer_config.AtomizerConfig) -> list[slice_frontmatter.Slice]:
        slice_ = slice_frontmatter.build(fragment, config)
        # If this is the target fragment, break validation by removing memory_layer
        if fragment.source_session == self.fail_session and fragment.fragment_index == self.fail_index:
            bad_fm = dict(slice_.frontmatter)
            del bad_fm["memory_layer"]  # This will fail T4 validation
            return [slice_frontmatter.Slice(slice_id=slice_.slice_id, frontmatter=bad_fm, body=slice_.body)]
        return [slice_]


class PipelineTests(unittest.TestCase):
    def test_split_pass_creates_fragments_and_archives_raw(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertFalse(raw.exists())  # raw archived out of raw layer
            self.assertTrue(list((root / "archive" / "sessions").rglob("*.md")))
            self.assertTrue(list((root / "knowledge").rglob("*.md")))
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")

    def test_one_to_one_slice_count_matches_fragments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(result["summary"]["slices"], 2)  # two headings -> two slices

    def test_idempotent_second_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            kwargs = dict(config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            pipeline.run(root, **kwargs)
            before = len(list((root / "knowledge").rglob("*.md")))
            result2 = pipeline.run(root, **kwargs)
            self.assertEqual(result2["summary"]["slices"], 0)
            self.assertEqual(len(list((root / "knowledge").rglob("*.md"))), before)

    def test_flow_through_empties_working_layers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])
            self.assertTrue(list((root / "archive" / "fragments").rglob("*.md")))

    def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", dry_run=True)
            self.assertTrue(raw.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertGreater(result["summary"]["slices"], 0)

    def test_unsafe_project_path_is_skipped_without_writing_outside_root(self):
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "memory"
            escaped = parent / "escaped"
            raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(_RAW.replace("project: paulshaclaw", "project: ../../../escaped"),
                           encoding="utf-8")
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")

            self.assertTrue(raw.exists())
            self.assertFalse(escaped.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertGreater(result["summary"]["skipped"], 0)
            self.assertTrue(any("unsafe path field" in w for w in result["warnings"]))

    def test_partial_promote_failure_then_retry(self):
        """
        Regression test for Task 7 review findings:
        1. If fragment N fails validation, fragments 0..N-1 should not have written slices/relations
        2. One bad split session should not block later split sessions
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)  # claude:s1
            _seed_raw_s2(root)  # claude:s2
            cfg, h = atomizer_config.load_config(override_path=None)
            
            # First run: split+promote with failing promoter that breaks s1 fragment 1
            # This should split both, but only promote s2 (s1 fails validation and stays split)
            kwargs = dict(config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            failing_promoter = FailingPromoter(fail_session="s1", fail_index=1)
            result = pipeline.run(root, **kwargs, promoter=failing_promoter)
            
            # Verify s1 is still split (failed validation)
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            
            # Verify s2 is promoted (should not be blocked by s1 failure)
            self.assertEqual(processing.state_of(root, "claude:s2"), "promoted")
            
            # Verify no knowledge slices for s1
            s1_slices = [p for p in (root / "knowledge" / "paulshaclaw").rglob("*.md") 
                        if "s1" in p.read_text()]
            self.assertEqual(len(s1_slices), 0, "s1 should not have any knowledge slices after failed promotion")
            
            # Verify s2 has knowledge slices
            s2_slices = [p for p in (root / "knowledge" / "paulshaclaw").rglob("*.md") 
                        if "s2" in p.read_text()]
            self.assertGreater(len(s2_slices), 0, "s2 should have knowledge slices")
            
            # Verify no promoted_to or distilled_from edges for s1
            edges = relations.read_edges(root)
            s1_promoted_edges = [e for e in edges if e["type"] == "promoted_to" and "__s1__" in e["from"]]
            s1_distilled_edges = [e for e in edges if e["type"] == "distilled_from" and "claude:s1" in e["to"]]
            self.assertEqual(len(s1_promoted_edges), 0, "s1 should not have promoted_to edges after failed promotion")
            self.assertEqual(len(s1_distilled_edges), 0, "s1 should not have distilled_from edges after failed promotion")
            
            # Verify warning was issued
            self.assertGreater(len(result["warnings"]), 0, "should have warning about failed validation")
            self.assertTrue(any("left in split" in w for w in result["warnings"]), 
                           "warning should mention leaving session in split")
            
            # Second run: retry with normal promoter (should promote s1 without duplicates)
            result2 = pipeline.run(root, **kwargs)
            
            # Verify s1 is now promoted
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            
            # Verify no duplicate edges: check that (type, from, to) triples are unique
            edges = relations.read_edges(root)
            edge_triples = [(e["type"], e["from"], e["to"]) for e in edges]
            self.assertEqual(len(edge_triples), len(set(edge_triples)), 
                           f"duplicate relation edges detected: {len(edge_triples)} total, {len(set(edge_triples))} unique")


if __name__ == "__main__":
    unittest.main()
