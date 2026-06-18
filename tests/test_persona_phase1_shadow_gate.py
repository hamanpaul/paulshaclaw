from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def _valid_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_role": "builder",
        "to_role": "reviewer",
        "phase": "review",
        "gate_status": "passed",
        "slice_id": "persona-phase1-shadow-gate",
        "summary": "phase1 shadow gate building blocks",
        "artifact_refs": ["feature/persona-phase1-shadow-gate"],
        "created_at": "2026-06-18T00:00:00+08:00",
        "base": "main",
        "head": "feature/persona-phase1-shadow-gate",
    }
    payload.update(overrides)
    return payload


class HandoffManifestTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        from paulshaclaw.persona import handoff

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "runtime" / "handoff" / "persona-phase1-shadow-gate.json"
            payload = _valid_manifest()
            handoff.write_manifest(path, payload)
            self.assertTrue(path.is_file())
            loaded = handoff.read_manifest(path)
            self.assertEqual(loaded, payload)

    def test_write_creates_parent_dirs(self) -> None:
        from paulshaclaw.persona import handoff

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a" / "b" / "c.json"
            handoff.write_manifest(path, _valid_manifest())
            self.assertTrue(path.is_file())

    def test_invalid_manifest_raises(self) -> None:
        from paulshaclaw.persona import handoff

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            # 缺 created_at 且 gate_status 非法 → validate_handoff_message 不過
            bad = _valid_manifest()
            del bad["created_at"]
            bad["gate_status"] = "bogus"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                handoff.read_manifest(path)

    def test_missing_file_fails_closed(self) -> None:
        from paulshaclaw.persona import handoff

        with self.assertRaises(Exception) as ctx:
            handoff.read_manifest("/nonexistent/handoff/x.json")
        # fail-closed：FileNotFoundError 或 ValueError 皆可，重點是 raise 而非回傳空
        self.assertIsInstance(ctx.exception, (FileNotFoundError, ValueError))


if __name__ == "__main__":
    unittest.main()
