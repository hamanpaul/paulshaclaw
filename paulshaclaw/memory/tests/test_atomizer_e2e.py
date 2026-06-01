from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.memory.atomizer import pipeline
from paulshaclaw.memory.ledger import processing, relations
from paulshaclaw.lifecycle.schema import parse_artifact_text, validate_frontmatter

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "atomizer" / "raw" / "s1.md"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _seed(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE, raw)
    return raw


def _cfg():
    return atomizer_config.load_config(override_path=None)


class AtomizerE2ETests(unittest.TestCase):
    def test_full_run_then_idempotent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(processing.state_of(root, "claude:sess-e2e"), "promoted")
            r2 = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T04:00:00Z")
            self.assertEqual(r2["summary"]["slices"], 0)

    def test_crash_resume_promote_completes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            warnings: list[str] = []
            pipeline._split_pass(root, cfg, h, "2026-05-31T03:00:00Z", False, warnings)
            self.assertEqual(processing.state_of(root, "claude:sess-e2e"), "split")
            self.assertTrue(list((root / "inbox" / "_slices").rglob("*.md")))
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:30:00Z")
            self.assertEqual(processing.state_of(root, "claude:sess-e2e"), "promoted")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])

    def test_reimport_overwrites_same_slice_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            slice_files = list((root / "knowledge").rglob("*.md"))
            ids_before = sorted(p.name for p in slice_files)
            raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(FIXTURE.read_text(encoding="utf-8").replace("alpha body", "ALPHA v2"),
                           encoding="utf-8")
            processing.processing_path(root).unlink()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T05:00:00Z")
            ids_after = sorted(p.name for p in (root / "knowledge").rglob("*.md"))
            self.assertEqual(ids_before, ids_after)
            self.assertIn("ALPHA v2", (root / "knowledge" / "paulshaclaw" / ids_after[0]).read_text())

    def test_produced_slice_passes_stage3_gate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            slice_path = next((root / "knowledge").rglob("*.md"))
            doc = parse_artifact_text(slice_path.read_text(encoding="utf-8"))
            result = validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body)
            self.assertTrue(result.ok, result.errors)

    def test_relations_have_distilled_from(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            edges = relations.neighbors(root, "session:claude:sess-e2e")
            self.assertTrue(any(e["type"] == "distilled_from" for e in edges))

    def test_ledgers_have_no_record_body(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            for name in ("processing.jsonl", "relations.jsonl"):
                raw = (root / "runtime" / "ledger" / name).read_text(encoding="utf-8")
                self.assertNotIn("alpha body", raw)
                self.assertNotIn("beta body", raw)


if __name__ == "__main__":
    unittest.main()
