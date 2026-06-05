from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import lifecycle
from paulshaclaw.memory.wakeup import build_brief


def _slice(root: Path, slice_id: str, project: str, title: str, body: str = None) -> None:
    body_text = body if body is not None else f"body {slice_id}\n"
    path = root / "knowledge" / project / f"{title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: {project}\n"
                    f"title: {title}\n---\n{body_text}", encoding="utf-8")


def _moc(root: Path, project: str, body: str) -> None:
    path = root / "knowledge" / f"{project}-moc.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class WakeupBuilderTests(unittest.TestCase):
    def test_map_and_recent_ordering(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC BODY\n")
            _slice(root, "sl-1", "p", "alpha")
            _slice(root, "sl-2", "p", "beta")
            _slice(root, "sl-3", "p", "gamma")
            # append events with increasing times
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-01-01T00:00:00Z")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-2", event_type="updated", source="x", reason="r", actor="a", ts="2026-02-01T00:00:00Z")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-3", event_type="accessed", source="x", reason="r", actor="a", ts="2026-03-01T00:00:00Z")
            out = build_brief(root, "p", now="2026-06-03T00:00:00Z", k=10)
            self.assertIn("# Memory wake-up — p", out)
            self.assertIn("MOC BODY", out)
            # recent ordering newest first: sl-3, sl-2, sl-1
            idx3 = out.find("sl-3")
            idx2 = out.find("sl-2")
            idx1 = out.find("sl-1")
            self.assertTrue(idx3 < idx2 < idx1)

    def test_unknown_project_returns_empty(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(build_brief(root, "_unknown", now="2026-06-03T00:00:00Z"), "")

    def test_empty_project_returns_empty(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(build_brief(root, "", now="2026-06-03T00:00:00Z"), "")

    def test_project_with_no_slices_returns_empty(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC BODY\n")
            # no slices
            self.assertEqual(build_brief(root, "p", now="2026-06-03T00:00:00Z"), "")

    def test_decayed_slice_excluded(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC BODY\n")
            _slice(root, "sl-1", "p", "alpha")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="decayed", source="janitor", reason="ttl", actor="janitor", ts="2026-04-01T00:00:00Z")
            self.assertEqual(build_brief(root, "p", now="2026-06-03T00:00:00Z"), "")

    def test_char_budget_truncates_map_tail_but_keeps_recent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            big = "".join([f"Line {i}\n" for i in range(1000)])
            _moc(root, "p", big)
            _slice(root, "sl-1", "p", "alpha")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-05-01T00:00:00Z")
            out = build_brief(root, "p", now="2026-06-03T00:00:00Z", char_budget=200)
            # budget contract: never exceed the provided char_budget
            self.assertLessEqual(len(out), 200)
            self.assertIn("## Recent", out)
            self.assertIn("(truncated)", out)

    def test_recent_summary_comes_from_body(self):
        # New TDD: ensure summary uses first non-empty line from the slice body, not title
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC\n")
            _slice(root, "sl-1", "p", "meta-title", body="First line summary\nSecond line\n")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-05-01T00:00:00Z")
            out = build_brief(root, "p", now="2026-06-03T00:00:00Z")
            # expect the recent entry to show the body-derived summary and enriched format
            self.assertIn("sl-1", out)
            self.assertIn("[[meta-title]]", out)
            self.assertIn("First line summary", out)
            self.assertIn("(2026-05-01T00:00:00Z)", out)
            self.assertNotIn("sl-1: meta-title", out)

    def test_map_header_present_even_under_tight_budget(self):
        # New TDD: when char budget is very tight, Map header must still be present and show (truncated)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            big = "".join([f"Line {i}\n" for i in range(1000)])
            _moc(root, "p", big)
            _slice(root, "sl-1", "p", "alpha")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-05-01T00:00:00Z")
            # very small budget to force tight behavior
            out = build_brief(root, "p", now="2026-06-03T00:00:00Z", char_budget=80)
            # budget contract
            self.assertLessEqual(len(out), 80)
            self.assertIn("## Map", out)
            self.assertIn("(truncated)", out)

    def test_strict_budget_never_exceeds(self):
        # ensure no code path can return more than the provided char_budget
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC BODY\n")
            _slice(root, "sl-1", "p", "alpha")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-05-01T00:00:00Z")
            # extremely tight budget intended to exercise extreme fallback
            out = build_brief(root, "p", now="2026-06-03T00:00:00Z", char_budget=5)
            self.assertLessEqual(len(out), 5)

    def test_preserve_recent_over_map_in_extreme_fallback(self):
        # prefer preserving Recent continuity when budget forces a hard choice
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC BODY\n")
            _slice(root, "sl-1", "p", "alpha")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-05-01T00:00:00Z")
            # small budget that should allow Recent but not a full Map body
            out = build_brief(root, "p", now="2026-06-03T00:00:00Z", char_budget=40)
            self.assertLessEqual(len(out), 40)
            self.assertIn("## Recent", out)
            # Map may be absent in this extreme case; if present it should show truncated marker
            self.assertTrue(("## Map" not in out) or ("(truncated)" in out))

    def test_deterministic_repeated_calls(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _moc(root, "p", "MOC BODY\n")
            _slice(root, "sl-1", "p", "alpha")
            lifecycle.append_event(path=root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="created", source="x", reason="r", actor="a", ts="2026-05-01T00:00:00Z")
            a = build_brief(root, "p", now="2026-06-03T00:00:00Z")
            b = build_brief(root, "p", now="2026-06-03T00:00:00Z")
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
