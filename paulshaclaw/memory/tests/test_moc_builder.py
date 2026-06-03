# paulshaclaw/memory/tests/test_moc_builder.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import lifecycle
from paulshaclaw.memory.moc import faceout, moc_builder


def _slice(root: Path, slice_id: str, project: str, title: str) -> None:
    body = f"body {slice_id}\n"
    path = root / "knowledge" / project / f"{title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: {project}\n"
                    f"artifact_kind: research\ntitle: {title}\n---\n{body}", encoding="utf-8")


class MocBuilderTests(unittest.TestCase):
    def test_three_mocs_with_moc_layer(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "prplos-core", "alpha")
            _slice(root, "sl-2", "common-sense", "rule-x")
            moc_builder.build_mocs(root, now="2026-06-03T00:00:00Z")
            project_moc = (root / "knowledge" / "prplos-core-moc.md").read_text(encoding="utf-8")
            self.assertIn("memory_layer: moc", project_moc)
            self.assertIn("[[alpha--sl-1]]", project_moc)
            cs = (root / "knowledge" / "common-sense-moc.md").read_text(encoding="utf-8")
            self.assertIn("[[rule-x--sl-2]]", cs)
            wiki = (root / "knowledge" / "wiki-moc.md").read_text(encoding="utf-8")
            self.assertIn("## Active", wiki)
            self.assertIn("[[alpha--sl-1]]", wiki)

    def test_faceout_lists_decayed_not_deleted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "p", "alpha")
            moc_builder.build_mocs(root, now="2026-06-03T00:00:00Z")
            lifecycle.append_event(
                path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                record_id="sl-1",
                event_type="decayed",
                source="janitor",
                reason="ttl_expired",
                actor="janitor"
            )
            faceout.mark_faceout(root)
            wiki = (root / "knowledge" / "wiki-moc.md").read_text(encoding="utf-8")
            self.assertIn("## Faceout", wiki)
            self.assertIn("sl-1", wiki)
            self.assertTrue((root / "knowledge" / "p" / "alpha--sl-1.md").exists())  # not deleted


if __name__ == "__main__":
    unittest.main()
