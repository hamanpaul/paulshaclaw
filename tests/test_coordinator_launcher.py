from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import paulshaclaw.coordinator.launcher as launcher_module
from paulshaclaw.coordinator.launcher import (
    SubprocessLauncher,
    build_copilot_argv,
    build_claude_argv,
    build_codex_argv,
)


class ArgvTests(unittest.TestCase):
    def test_copilot_argv(self) -> None:
        argv = build_copilot_argv(prompt="PROMPT", slice_id="slice-a", log_dir="/lg")
        self.assertEqual(argv[0], "copilot")
        self.assertIn("-p", argv)
        self.assertIn("PROMPT", argv)                 # prompt 為單一元素
        self.assertIn("--remote", argv)
        self.assertIn("--name", argv)
        self.assertIn("slice-a", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("json", argv)

    def test_claude_argv(self) -> None:
        argv = build_claude_argv(
            prompt="PROMPT",
            slice_id="slice-a",
            log_dir="/lg",
            worktree="/wt/slice-a",
        )
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("PROMPT", argv)
        self.assertIn("--remote-control", argv)
        self.assertIn("--add-dir", argv)
        self.assertIn("/wt/slice-a", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("stream-json", argv)
        self.assertIn("--name", argv)
        self.assertIn("slice-a", argv)
        self.assertIn("--permission-mode", argv)
        self.assertIn("acceptEdits", argv)

    def test_codex_argv(self) -> None:
        argv = build_codex_argv(
            prompt="PROMPT",
            slice_id="slice-a",
            log_dir="/lg",
            worktree="/wt/slice-a",
            remote="unix:/tmp/psc.sock",
        )
        self.assertEqual(argv[0], "codex")
        self.assertIn("exec", argv)
        self.assertIn("PROMPT", argv)
        self.assertIn("--remote", argv)
        self.assertIn("unix:/tmp/psc.sock", argv)
        self.assertIn("-C", argv)
        self.assertIn("/wt/slice-a", argv)
        self.assertIn("--json", argv)
        self.assertIn("-o", argv)

    def test_prompt_is_single_element(self) -> None:
        # prompt 含換行也是單一 argv 元素（headless 的核心保證）
        argv = build_copilot_argv(prompt="line1\nline2", slice_id="s", log_dir="/lg")
        self.assertIn("line1\nline2", argv)

    def test_subprocess_launcher_injects_slice_and_relay_target_env(self) -> None:
        calls = []

        class _FakeProc:
            pid = 456

        def _fake_popen(argv, *, cwd, env, stdout, stderr):
            calls.append({"argv": argv, "cwd": cwd, "env": env})
            return _FakeProc()

        original = launcher_module.subprocess.Popen
        launcher_module.subprocess.Popen = _fake_popen
        try:
            with tempfile.TemporaryDirectory() as d:
                log_dir = Path(d) / "logs"
                handle = SubprocessLauncher(
                    "copilot",
                    relay_target="/tmp/relay.out",
                ).launch(
                    slice_id="slice-a",
                    prompt="PROMPT",
                    worktree=d,
                    log_dir=str(log_dir),
                )
        finally:
            launcher_module.subprocess.Popen = original

        self.assertEqual(handle.pid, 456)
        self.assertEqual(calls[0]["env"]["PSC_SLICE_ID"], "slice-a")
        self.assertEqual(calls[0]["env"]["PSC_RELAY_TARGET"], "/tmp/relay.out")


if __name__ == "__main__":
    unittest.main()
