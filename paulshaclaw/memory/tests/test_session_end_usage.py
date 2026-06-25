from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.usage_ledger import record_session_usage


def _offered(root: Path, tool: str, sid: str):
    d = root / "runtime" / "wakeup"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tool}__{sid}.json").write_text(json.dumps({
        "session_id": sid, "tool": tool, "ts": "2026-06-25T00:00:00Z",
        "offered": [{"id": "sl-1234567890abcdef", "title": "Some Long Title Here"},
                    {"id": "sl-fedcba0987654321", "title": "Another Long Title Here"}],
    }, ensure_ascii=False), encoding="utf-8")


def _transcript(root: Path, lines: list[dict]) -> Path:
    p = root / "t.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return p


class RecordUsageTests(unittest.TestCase):
    def test_writes_event_with_offered_id_array(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _offered(root, "claude-code", "s1")
            tp = _transcript(root, [
                {"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "我用了 [[sl-1234567890abcdef]] 來解決。"}]}},
                {"type": "user", "message": {"role": "user",
                 "content": [{"type": "text", "text": "Another Long Title Here"}]}},
            ])
            record_session_usage(root, "claude-code", "s1", "paulshaclaw", str(tp))
            rows = [json.loads(l) for l in (root / "runtime" / "ledger" / "memory_usage.jsonl").read_text().splitlines() if l.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["offered"], ["sl-1234567890abcdef", "sl-fedcba0987654321"])
            self.assertEqual(rows[0]["cited"], ["sl-1234567890abcdef"])
            self.assertEqual(rows[0]["matched"], [])

    def test_missing_offered_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tp = _transcript(root, [{"type": "assistant", "message": {"role": "assistant",
                                     "content": [{"type": "text", "text": "x"}]}}])
            record_session_usage(root, "claude-code", "nope", "p", str(tp))
            self.assertFalse((root / "runtime" / "ledger" / "memory_usage.jsonl").exists())

    def test_missing_transcript_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _offered(root, "claude-code", "s3")
            record_session_usage(root, "claude-code", "s3", "p", str(root / "nope.jsonl"))
            self.assertFalse((root / "runtime" / "ledger" / "memory_usage.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
