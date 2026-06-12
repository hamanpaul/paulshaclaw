# paulshaclaw/memory/tests/test_moc_search.py
from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory.moc import search
from paulshaclaw.memory.moc import frontmatter_io as fio


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

    def test_build_index_batches_active_record_lookups(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(205):
                _slice(root, f"sl-{index:03d}", "proj", f"title-{index:03d}", f"body {index}")

            batch_sizes: list[int] = []

            def fake_active_records(memory_root: Path, record_ids: list[str]) -> list[str]:
                batch_sizes.append(len(record_ids))
                return record_ids

            with mock.patch(
                "paulshaclaw.memory.moc.search.retrieval_set.active_records",
                side_effect=fake_active_records,
            ):
                search.build_index(root, link_weights={})

            self.assertGreater(len(batch_sizes), 1)
            self.assertTrue(all(size <= 100 for size in batch_sizes), batch_sizes)
            self.assertEqual(sum(batch_sizes), 205)

    def test_build_index_matches_legacy_row_contents(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "proj", "alpha", "alpha body")
            _slice(root, "sl-2", "proj", "beta", "beta body")
            path = root / "knowledge" / "proj" / "ignored.md"
            path.write_text("---\nmemory_layer: inbox\nproject: proj\ntitle: ignored\n---\nignore\n", encoding="utf-8")
            expected = self._legacy_rows(root, active_ids={"sl-2"}, link_weights={"sl-1": 4, "sl-2": 0})

            with mock.patch(
                "paulshaclaw.memory.moc.search.retrieval_set.active_records",
                side_effect=lambda memory_root, record_ids: [rid for rid in record_ids if rid == "sl-2"],
            ):
                search.build_index(root, link_weights={"sl-1": 4, "sl-2": 0})

            conn = sqlite3.connect(search.index_path(root))
            try:
                rows = conn.execute(
                    "SELECT slice_id, project, captured_at, active, link_weight FROM slice_meta ORDER BY slice_id"
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(rows, expected)

    def _legacy_rows(
        self,
        root: Path,
        *,
        active_ids: set[str],
        link_weights: dict[str, int],
    ) -> list[tuple[str, str, str, int, int]]:
        rows: list[tuple[str, str, str, int, int]] = []
        for fpath in sorted((root / "knowledge").rglob("*.md")):
            fm, body = fio.read(fpath.read_text(encoding="utf-8"))
            if fm.get("memory_layer") != "knowledge":
                continue
            sid = fm.get("slice_id")
            if not sid:
                continue
            rows.append(
                (
                    str(sid),
                    str(fm.get("project", "")),
                    str(fm.get("captured_at", "")),
                    1 if str(sid) in active_ids else 0,
                    link_weights.get(str(sid), 0),
                )
            )
        return rows


if __name__ == "__main__":
    unittest.main()
