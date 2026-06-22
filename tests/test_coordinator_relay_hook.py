from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = "scripts/coordinator/psc-relay-hook.sh"


class RelayHookTests(unittest.TestCase):
    def test_emits_slice_tagged_payload(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "relay.out"
            env = {**os.environ, "PSC_SLICE_ID": "slice-a",
                   "PSC_RELAY_TARGET": str(out), "PSC_RELAY_EVENT": "stop"}
            subprocess.run(["bash", HOOK], env=env, check=True)
            text = out.read_text(encoding="utf-8")
            self.assertIn("slice-a", text)
            self.assertIn("stop", text)

    def test_missing_target_does_not_fail(self) -> None:
        # relay 失敗（無 target）MUST NOT 非零退出（fire-and-forget）
        env = {**os.environ, "PSC_SLICE_ID": "slice-a", "PSC_RELAY_EVENT": "stop"}
        env.pop("PSC_RELAY_TARGET", None)
        r = subprocess.run(["bash", HOOK], env=env)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
