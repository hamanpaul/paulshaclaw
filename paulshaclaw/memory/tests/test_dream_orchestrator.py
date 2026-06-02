"""Tests for dream orchestrator (Stage 2 Task 4).

These tests assert the *plan-shaped* contract for Task 4.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.dream import orchestrator
from paulshaclaw.memory.ledger import dream


class TestDreamOrchestrator(unittest.TestCase):
    def test_runs_passes_in_order_and_persists_ok(self):
        calls: list[str] = []

        def atomize_fn():
            calls.append("a")
            return {"summary": {"skipped": 0}, "warnings": []}

        def janitor_fn():
            calls.append("j")
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            orchestrator.run_dream(
                root,
                atomize_fn=atomize_fn,
                janitor_fn=janitor_fn,
                now="2026-06-02T00:00:00Z",
                config_hash="cfg",
            )

            self.assertEqual(calls, ["a", "j"])
            record = dream.last_run(root)
            self.assertIsNotNone(record)
            self.assertEqual(record["run_id"], "dream-2026-06-02T00:00:00Z")
            self.assertEqual(record["passes"]["atomize"], {"skipped": 0})
            self.assertEqual(record["passes"]["janitor"], {"skipped": 0})
            self.assertEqual(record["status"], "ok")

    def test_janitor_runs_even_if_atomize_raises(self):
        calls: list[str] = []

        def atomize_fn():
            calls.append("a")
            raise RuntimeError("boom")

        def janitor_fn():
            calls.append("j")
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            orchestrator.run_dream(
                root,
                atomize_fn=atomize_fn,
                janitor_fn=janitor_fn,
                now="2026-06-02T00:00:00Z",
                config_hash="cfg",
            )

            self.assertEqual(calls, ["a", "j"])

    def test_warnings_produce_partial(self):
        def atomize_fn():
            return {"summary": {"skipped": 0}, "warnings": ["warn"]}

        def janitor_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            orchestrator.run_dream(
                root,
                atomize_fn=atomize_fn,
                janitor_fn=janitor_fn,
                now="2026-06-02T00:00:00Z",
                config_hash="cfg",
            )

            self.assertEqual(dream.last_run(root)["status"], "partial")

    def test_dry_run_writes_no_ledger(self):
        def atomize_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        def janitor_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            orchestrator.run_dream(
                root,
                atomize_fn=atomize_fn,
                janitor_fn=janitor_fn,
                now="2026-06-02T00:00:00Z",
                config_hash="cfg",
                dry_run=True,
            )

            self.assertIsNone(dream.last_run(root))


if __name__ == "__main__":
    unittest.main()
