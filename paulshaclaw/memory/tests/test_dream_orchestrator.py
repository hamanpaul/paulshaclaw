"""Tests for dream orchestrator (Stage 2 Task 4).

TDD note: this test module is expected to fail-import until
paulshaclaw.memory.dream.orchestrator is implemented.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


class TestDreamOrchestrator(unittest.TestCase):
    def test_both_passes_run_in_order_and_status_ok(self):
        from paulshaclaw.memory.dream.orchestrator import run_dream

        calls: list[str] = []

        def atomize_fn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
            calls.append("atomize")
            return {"summary": {"skipped": 0}, "warnings": []}

        def janitor_fn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
            calls.append("janitor")
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with mock.patch("paulshaclaw.memory.ledger.dream.append_run") as append_run:
                record = run_dream(
                    root,
                    atomize_fn=atomize_fn,
                    janitor_fn=janitor_fn,
                    now="2026-06-02T00:00:00Z",
                    config_hash="cfg",
                )

            self.assertEqual(calls, ["atomize", "janitor"])
            self.assertEqual(record["status"], "ok")
            self.assertEqual(record["ts"], "2026-06-02T00:00:00Z")
            self.assertEqual(record["dream_config_hash"], "cfg")
            self.assertFalse(record["dry_run"])
            self.assertIsInstance(record.get("run_id"), str)
            self.assertTrue(record.get("run_id"))
            self.assertIn("atomize", record["passes"])
            self.assertIn("janitor", record["passes"])
            self.assertEqual(record["errors"], [])
            append_run.assert_called_once()
            args, _kwargs = append_run.call_args
            self.assertEqual(args[0], root)
            self.assertEqual(args[1], record)

    def test_atomize_failure_does_not_block_janitor_and_status_failed(self):
        from paulshaclaw.memory.dream.orchestrator import run_dream

        calls: list[str] = []

        def atomize_fn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
            calls.append("atomize")
            raise ValueError("boom")

        def janitor_fn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
            calls.append("janitor")
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with mock.patch("paulshaclaw.memory.ledger.dream.append_run"):
                record = run_dream(
                    root,
                    atomize_fn=atomize_fn,
                    janitor_fn=janitor_fn,
                    now="2026-06-02T00:00:00Z",
                    config_hash="cfg",
                )

        self.assertEqual(calls, ["atomize", "janitor"])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(record["errors"]), 1)
        self.assertEqual(record["errors"][0]["pass"], "atomize")
        self.assertEqual(record["errors"][0]["exc_type"], "ValueError")
        self.assertIn("boom", record["errors"][0]["message"])
        self.assertEqual(record["passes"]["janitor"]["status"], "ok")

    def test_warnings_or_skipped_make_status_partial(self):
        from paulshaclaw.memory.dream.orchestrator import run_dream

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            def atomize_warn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
                return {"summary": {"skipped": 0}, "warnings": ["something odd"]}

            def janitor_ok(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
                return {"summary": {"skipped": 0}, "warnings": []}

            with mock.patch("paulshaclaw.memory.ledger.dream.append_run"):
                record = run_dream(
                    root,
                    atomize_fn=atomize_warn,
                    janitor_fn=janitor_ok,
                    now="2026-06-02T00:00:00Z",
                    config_hash="cfg",
                )
            self.assertEqual(record["status"], "partial")

            def atomize_ok(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
                return {"summary": {"skipped": 0}, "warnings": []}

            def janitor_skipped(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
                return {"summary": {"skipped": 2}, "warnings": []}

            with mock.patch("paulshaclaw.memory.ledger.dream.append_run"):
                record2 = run_dream(
                    root,
                    atomize_fn=atomize_ok,
                    janitor_fn=janitor_skipped,
                    now="2026-06-02T00:00:01Z",
                    config_hash="cfg",
                )
            self.assertEqual(record2["status"], "partial")

    def test_dry_run_writes_no_dream_ledger_record(self):
        from paulshaclaw.memory.dream.orchestrator import run_dream

        def atomize_fn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
            return {"summary": {"skipped": 0}, "warnings": []}

        def janitor_fn(memory_root: Path, *, now: str, config_hash: str, dry_run: bool = False):
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with mock.patch("paulshaclaw.memory.ledger.dream.append_run") as append_run:
                record = run_dream(
                    root,
                    atomize_fn=atomize_fn,
                    janitor_fn=janitor_fn,
                    now="2026-06-02T00:00:00Z",
                    config_hash="cfg",
                    dry_run=True,
                )

        self.assertTrue(record["dry_run"])
        append_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
