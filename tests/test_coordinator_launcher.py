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
        self.assertIn("--verbose", argv)  # smoke: -p+stream-json 必須帶 --verbose
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
        self.assertNotIn("--remote", argv)  # smoke: codex exec 不吃 --remote（unexpected argument）
        self.assertNotIn("unix:/tmp/psc.sock", argv)
        self.assertIn("-C", argv)
        self.assertIn("/wt/slice-a", argv)
        self.assertIn("--json", argv)
        self.assertIn("-o", argv)

    def test_codex_argv_default_has_no_sandbox_bypass(self) -> None:
        # 預設（allow_unsafe 未開）不得帶 --dangerously-bypass-approvals-and-sandbox（高風險）
        argv = build_codex_argv(prompt="P", slice_id="s", log_dir="/lg")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_codex_argv_allow_unsafe_adds_sandbox_bypass(self) -> None:
        # 明確 opt-in allow_unsafe=True 才加入 sandbox bypass flag
        argv = build_codex_argv(prompt="P", slice_id="s", log_dir="/lg", allow_unsafe=True)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_subprocess_launcher_codex_default_no_sandbox_bypass(self) -> None:
        import shlex

        calls = []

        class _FakeProc:
            pid = 111

        def _fake_popen(argv, *, cwd, env, stdout, stderr):
            calls.append({"argv": argv})
            return _FakeProc()

        original = launcher_module.subprocess.Popen
        launcher_module.subprocess.Popen = _fake_popen
        try:
            with tempfile.TemporaryDirectory() as d:
                SubprocessLauncher("codex").launch(
                    slice_id="s", prompt="P", worktree=d, log_dir=str(Path(d) / "lg"),
                )
        finally:
            launcher_module.subprocess.Popen = original
        script = calls[0]["argv"][2]
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", script)

    def test_subprocess_launcher_codex_allow_unsafe_adds_sandbox_bypass(self) -> None:
        calls = []

        class _FakeProc:
            pid = 222

        def _fake_popen(argv, *, cwd, env, stdout, stderr):
            calls.append({"argv": argv})
            return _FakeProc()

        original = launcher_module.subprocess.Popen
        launcher_module.subprocess.Popen = _fake_popen
        try:
            with tempfile.TemporaryDirectory() as d:
                SubprocessLauncher("codex", allow_unsafe=True).launch(
                    slice_id="s", prompt="P", worktree=d, log_dir=str(Path(d) / "lg"),
                )
        finally:
            launcher_module.subprocess.Popen = original
        script = calls[0]["argv"][2]
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", script)

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

    def test_subprocess_launcher_wraps_with_exit_sentinel(self) -> None:
        import shlex

        from paulshaclaw.coordinator.dispatcher import exit_sentinel_path

        calls = []

        class _FakeProc:
            pid = 789

        def _fake_popen(argv, *, cwd, env, stdout, stderr):
            calls.append({"argv": argv})
            return _FakeProc()

        original = launcher_module.subprocess.Popen
        launcher_module.subprocess.Popen = _fake_popen
        try:
            with tempfile.TemporaryDirectory() as d:
                log_dir = Path(d) / "logs"
                handle = SubprocessLauncher("copilot").launch(
                    slice_id="slice-a",
                    prompt="PROMPT",
                    worktree=d,
                    log_dir=str(log_dir),
                )
        finally:
            launcher_module.subprocess.Popen = original

        argv = calls[0]["argv"]
        # 子進程經 bash -lc 包裝，結束時把 $? 寫到 sentinel（跨進程 durable 完成判定）
        self.assertEqual(argv[0], "bash")
        self.assertEqual(argv[1], "-lc")
        script = argv[2]
        sentinel = str(exit_sentinel_path(handle.log_path))
        self.assertIn(shlex.quote(sentinel), script)
        self.assertIn('"$?"', script)
        # 內層 argv 經 shlex.join 安全嵌入；含 -p PROMPT
        inner = shlex.join(["copilot", "-p", "PROMPT"])
        self.assertIn(inner, script)

    def test_subprocess_launcher_clears_stale_sentinel_and_truncates_log(self) -> None:
        # 同一 slice_id 重跑：上一輪殘留的 .exit/.jsonl 必須在 launch 前清掉，
        # 否則 poll_headless_done 會讀到舊 sentinel → 誤判「還沒開始就完成了」。
        from paulshaclaw.coordinator.dispatcher import exit_sentinel_path

        class _FakeProc:
            pid = 333

        def _fake_popen(argv, *, cwd, env, stdout, stderr):
            return _FakeProc()

        original = launcher_module.subprocess.Popen
        launcher_module.subprocess.Popen = _fake_popen
        try:
            with tempfile.TemporaryDirectory() as d:
                log_dir = Path(d) / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                stale_log = log_dir / "slice-a.jsonl"
                stale_exit = log_dir / "slice-a.exit"
                stale_log.write_text("STALE-PREV-ROUND\n", encoding="utf-8")
                stale_exit.write_text("0", encoding="utf-8")

                handle = SubprocessLauncher("copilot").launch(
                    slice_id="slice-a",
                    prompt="PROMPT",
                    worktree=d,
                    log_dir=str(log_dir),
                )

                # 舊 sentinel 在 launch 當下/前已被移除（fail-closed 防誤判完成）
                self.assertFalse(
                    exit_sentinel_path(handle.log_path).is_file(),
                    "stale .exit sentinel must be cleared before launch",
                )
                # log 以 wb 開啟（truncate）→ 不含上一輪內容
                self.assertNotIn("STALE-PREV-ROUND", Path(handle.log_path).read_text())
        finally:
            launcher_module.subprocess.Popen = original

    def test_subprocess_launcher_sentinel_records_real_exit_code(self) -> None:
        # 真跑 bash -lc 包裝，但內層 argv 覆寫成無害的 `exit 7`（絕不啟動真 copilot/codex），
        # 驗證 sentinel 確實寫下內層命令的真實 exit code（跨進程 durable 機制端到端）。
        import time

        from paulshaclaw.coordinator.dispatcher import exit_sentinel_path

        orig_builders = dict(launcher_module._ARGV_BUILDERS)
        launcher_module._ARGV_BUILDERS["copilot"] = (
            lambda **_kw: ["sh", "-c", "exit 7"]
        )
        try:
            with tempfile.TemporaryDirectory() as d:
                log_dir = Path(d) / "logs"
                handle = SubprocessLauncher("copilot").launch(
                    slice_id="slice-z",
                    prompt="PROMPT",
                    worktree=d,
                    log_dir=str(log_dir),
                )
                sentinel = exit_sentinel_path(handle.log_path)
                for _ in range(50):  # 短輪詢等子進程退出並寫 sentinel（避免 flaky）
                    if sentinel.is_file() and sentinel.read_text().strip():
                        break
                    time.sleep(0.05)
                # 斷言 MUST 在 with 內（tmpdir 尚未清除）
                self.assertTrue(sentinel.is_file(), "sentinel exit 檔應由 bash 包裝寫出")
                self.assertEqual(sentinel.read_text().strip(), "7")
        finally:
            launcher_module._ARGV_BUILDERS.clear()
            launcher_module._ARGV_BUILDERS.update(orig_builders)


if __name__ == "__main__":
    unittest.main()
