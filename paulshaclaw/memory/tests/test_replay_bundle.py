from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.replay import bundle


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _tmp_dir():
    return TemporaryDirectory(dir=_REPO_ROOT)


def _slice(root: Path, slice_id: str) -> Path:
    path = root / "knowledge" / "p" / f"{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"slice_id: {slice_id}\n"
        "project: p\n"
        "memory_layer: knowledge\n"
        "distilled_from: claude:s1\n"
        "---\n"
        f"DISTILLED {slice_id}\n",
        encoding="utf-8",
    )
    return path


def _raw_inbox(root: Path) -> Path:
    path = root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "memory_layer: inbox\n"
        "project: p\n"
        "source_agent: claude\n"
        "source_session: s1\n"
        "source_artifact: research\n"
        "captured_at: 2026-06-02T00:00:00Z\n"
        "---\n"
        "RAW PROMPT CONTENT\n",
        encoding="utf-8",
    )
    return path


class ReplayBundleTests(unittest.TestCase):
    def test_build_writes_manifest_slices_ledger_and_excludes_raw(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            _raw_inbox(root)
            s = _slice(root, "sl-1")
            out = root / "bundle-out"

            bundle.build(root, [s], out, selection={"project": "p"}, now="2026-06-02T06:00:00Z")

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["raw_excluded"])
            self.assertEqual(manifest["counts"]["slices"], 1)
            self.assertTrue((out / "slices" / "sl-1.md").exists())
            self.assertTrue((out / "ledger.jsonl").exists())

            blob = "".join(
                p.read_text(encoding="utf-8")
                for p in out.rglob("*")
                if p.is_file()
            )
            self.assertIn("DISTILLED", blob)
            self.assertNotIn("RAW PROMPT CONTENT", blob)

    def test_empty_selection_writes_empty_bundle(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            out = root / "bundle-out"

            bundle.build(root, [], out, selection={"project": "none"}, now="2026-06-02T06:00:00Z")

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["slices"], 0)


if __name__ == "__main__":
    unittest.main()
