from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory.hooks import _wakeup_common as wc


class WakeupOfferedTests(unittest.TestCase):
    def test_non_empty_brief_gets_preamble_and_writes_offered(self):
        brief = "# wake\n- [[foo--sl-1234567890abcdef|Some Title]] — spec\n"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(wc, "compute_brief", return_value=brief):
                out = wc.compute_brief_and_record(root, "claude-code", "sess1", cwd="/x")
            self.assertTrue(out.startswith("> 記憶使用追蹤"))
            offered_file = root / "runtime" / "wakeup" / "claude-code__sess1.json"
            self.assertTrue(offered_file.exists())
            data = json.loads(offered_file.read_text(encoding="utf-8"))
            self.assertEqual(data["offered"], [{"id": "sl-1234567890abcdef", "title": "Some Title"}])

    def test_empty_brief_no_preamble_no_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(wc, "compute_brief", return_value=""):
                out = wc.compute_brief_and_record(root, "claude-code", "sess2", cwd="/x")
            self.assertEqual(out, "")
            self.assertFalse((root / "runtime" / "wakeup" / "claude-code__sess2.json").exists())


if __name__ == "__main__":
    unittest.main()
