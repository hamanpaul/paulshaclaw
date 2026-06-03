# paulshaclaw/memory/tests/test_moc_search.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.moc import search


def _slice(root: Path, slice_id: str, project: str, title: str, body: str) -> None:
    path = root / "knowledge" / project / f"{title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: {project}\n"
                    f"title: {title}\ntags: [t]\ncaptured_at: 2026-06-03T00:00:00Z\n---\n{body}\n",
                    encoding="utf-8")


class SearchTests(unittest.TestCase):
    def test_build_and_query_with_project_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "prplos-core", "flock-ledger", "flock locking on ledger")
            _slice(root, "sl-2", "other", "unrelated", "different content")
            search.build_index(root, link_weights={"sl-1": 3, "sl-2": 0})
            hits = search.search(root, "flock", project="prplos-core", limit=5, include_decayed=True)
            self.assertEqual([h["slice_id"] for h in hits], ["sl-1"])
            self.assertIn("project", hits[0])

    def test_missing_index_raises(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(search.SearchIndexError):
                search.search(Path(tmp), "x", project=None, limit=5, include_decayed=False)


if __name__ == "__main__":
    unittest.main()
