from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from paulshaclaw.coordinator import cli
from paulshaclaw.coordinator.registry import JobRegistry
from paulshaclaw.coordinator.seams import PaneSender, WorktreeCreator


class _FakeSender(PaneSender):
    def send(self, *a, **k):  # pragma: no cover
        raise AssertionError("tick 不應送 pane")


class _FakeCreator(WorktreeCreator):
    def create(self, *a, **k):  # pragma: no cover
        raise AssertionError("tick 不應建 worktree")


class CliTickTests(unittest.TestCase):
    def test_tick_idle_skip_prints_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            specs = Path(d) / "specs"
            specs.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(
                    ["tick", "--specs-dir", str(specs), "--require-idle", "--max-load=-1"],
                    registry=reg, pane_sender=_FakeSender(), worktree_creator=_FakeCreator(),
                )
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["skipped"], "not-idle")


if __name__ == "__main__":
    unittest.main()
