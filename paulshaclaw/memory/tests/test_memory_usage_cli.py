from __future__ import annotations

import json
import unittest
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.cli import main


def _ledger(root: Path, events: list[dict]):
    d = root / "runtime" / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    (d / "memory_usage.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8")


class UsageCliTests(unittest.TestCase):
    def test_aggregates_and_counts_never_used(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ledger(root, [
                {"ts": "2026-06-25T01:00:00Z", "session_id": "a", "offered": ["sl-aaa", "sl-bbb"],
                 "cited": ["sl-aaa"], "matched": []},
                {"ts": "2026-06-25T02:00:00Z", "session_id": "b", "offered": ["sl-bbb"],
                 "cited": [], "matched": []},
            ])
            buf = StringIO()
            with redirect_stdout(buf):
                rc = main(["memory", "usage", "--memory-root", str(root), "--json"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            by = {s["slice_id"]: s for s in out["slices"]}
            self.assertEqual(by["sl-aaa"]["cited_count"], 1)
            self.assertEqual(by["sl-bbb"]["offered_count"], 2)
            self.assertEqual(by["sl-bbb"]["cited_count"], 0)
            self.assertEqual(out["summary"]["never_used"], 1)

    def test_works_without_wakeup_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ledger(root, [{"ts": "2026-06-25T01:00:00Z", "session_id": "a",
                            "offered": ["sl-aaa"], "cited": [], "matched": ["sl-aaa"]}])
            buf = StringIO()
            with redirect_stdout(buf):
                rc = main(["memory", "usage", "--memory-root", str(root), "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["summary"]["never_used"], 0)


if __name__ == "__main__":
    unittest.main()
