from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.moc import naming


def _write(root: Path, name: str, fm_extra: str, body: str = "body\n") -> Path:
    path = root / "knowledge" / "paulshaclaw" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {fm_extra}\nmemory_layer: knowledge\nproject: paulshaclaw\n"
                    f"artifact_kind: research\n---\n{body}", encoding="utf-8")
    return path


class NamingTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(naming.slugify("PWHM FSM States!"), "pwhm-fsm-states")

    def test_reconcile_renames_to_title_slice(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "knowledge" / "paulshaclaw" / "sl-1.md"
            p.parent.mkdir(parents=True)
            p.write_text("---\nslice_id: sl-1\nmemory_layer: knowledge\nproject: paulshaclaw\n"
                         "artifact_kind: research\ntitle: Alpha Note\n---\nbody\n", encoding="utf-8")
            naming.reconcile(root)
            self.assertFalse(p.exists())
            self.assertTrue((root / "knowledge" / "paulshaclaw" / "alpha-note--sl-1.md").exists())

    def test_title_fallback_to_artifact_project(self):
        # no title, no heading -> <artifact_kind>-<project>
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "sl-2.md", "sl-2")
            naming.reconcile(root)
            self.assertTrue((root / "knowledge" / "paulshaclaw" / "research-paulshaclaw--sl-2.md").exists())

    def test_dedup_keeps_one_per_slice_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kdir = root / "knowledge" / "paulshaclaw"
            kdir.mkdir(parents=True)
            (kdir / "sl-3.md").write_text("---\nslice_id: sl-3\nmemory_layer: knowledge\nproject: paulshaclaw\nartifact_kind: research\n---\nNEW\n", encoding="utf-8")
            (kdir / "old--sl-3.md").write_text("---\nslice_id: sl-3\nmemory_layer: knowledge\nproject: paulshaclaw\nartifact_kind: research\n---\nOLD\n", encoding="utf-8")
            naming.reconcile(root)
            remaining = sorted(p.name for p in kdir.glob("*sl-3*.md"))
            self.assertEqual(len(remaining), 1)

    def test_skips_moc_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            moc = root / "knowledge" / "wiki-moc.md"
            moc.parent.mkdir(parents=True)
            moc.write_text("---\nmemory_layer: moc\nmoc_kind: wiki\n---\n# Wiki\n", encoding="utf-8")
            naming.reconcile(root)
            self.assertTrue(moc.exists())  # untouched


if __name__ == "__main__":
    unittest.main()
