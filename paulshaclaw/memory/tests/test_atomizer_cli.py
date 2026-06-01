from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory import cli

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha
"""


class AtomizeCliTests(unittest.TestCase):
    def test_dry_run_prints_summary_and_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
            raw.parent.mkdir(parents=True)
            raw.write_text(_RAW, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["memory", "atomize", "--memory-root", str(root),
                               "--now", "2026-05-31T03:00:00Z", "--dry-run"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertGreaterEqual(payload["summary"]["slices"], 1)
            self.assertTrue(raw.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
