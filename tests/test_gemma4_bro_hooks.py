import importlib.util
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "scripts" / "gemma4-hooks"

def _load(name):
    loader = SourceFileLoader(name, str(HOOKS / f"{name}.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    import sys as _sys; _sys.modules[name] = module
    loader.exec_module(module)
    return module

class BroInTests(unittest.TestCase):
    def setUp(self):
        self.bro_in = _load("bro_in")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def test_bro_prompt_writes_user_id(self):
        self.bro_in.handle({"session_id": "s1", "prompt": "[bro:8313353234] 早安"}, self.state)
        data = json.loads((self.state / "s1.json").read_text(encoding="utf-8"))
        self.assertEqual(data["user_id"], 8313353234)

    def test_non_bro_prompt_clears_existing_statefile(self):
        (self.state / "s1.json").write_text('{"user_id": 1}', encoding="utf-8")
        self.bro_in.handle({"session_id": "s1", "prompt": "hello"}, self.state)
        self.assertFalse((self.state / "s1.json").exists())

    def test_missing_session_id_is_noop(self):
        self.bro_in.handle({"prompt": "[bro:1] hi"}, self.state)
        self.assertEqual(list(self.state.glob("*.json")), [])

class BroOutTests(unittest.TestCase):
    def setUp(self):
        self.bro_out = _load("bro_out")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.sent = []

    def _sender(self, user_id, text):
        self.sent.append((user_id, text))

    def _transcript(self, records):
        p = Path(self.tmp.name) / "t.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        return p

    def test_sends_last_assistant_text_to_stashed_user(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "first"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "final answer"}]}},
        ])
        sent = self.bro_out.handle(
            {"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender
        )
        self.assertTrue(sent)
        self.assertEqual(self.sent, [(7, "final answer")])
        self.assertFalse((self.state / "s1.json").exists())

    def test_sends_current_turn_reply_not_previous(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "PREVIOUS"}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "[bro:7] new question"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "CURRENT"}]}},
        ])
        self.bro_out.handle(
            {"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender, wait_seconds=0
        )
        self.assertEqual(self.sent, [(7, "CURRENT")])

    def test_does_not_send_previous_reply_when_current_not_flushed(self):
        # Transcript ends with the just-submitted user prompt; this turn's
        # assistant record hasn't been written yet. Must NOT fall back to the
        # previous turn's reply (the off-by-one). With no wait it sends the notice.
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "PREVIOUS"}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "[bro:7] new question"}]}},
        ])
        self.bro_out.handle(
            {"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender, wait_seconds=0
        )
        self.assertEqual(self.sent, [(7, "（已完成，無文字輸出）")])

    def test_empty_final_text_sends_notice(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "x", "input": {}}]}},
        ])
        self.bro_out.handle({"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender)
        self.assertEqual(self.sent, [(7, "（已完成，無文字輸出）")])

    def test_no_statefile_is_noop(self):
        t = self._transcript([{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}])
        self.assertFalse(self.bro_out.handle({"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender))
        self.assertEqual(self.sent, [])

    def test_stop_hook_active_is_noop(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        self.assertFalse(self.bro_out.handle({"session_id": "s1", "stop_hook_active": True}, self.state, sender=self._sender))
        self.assertEqual(self.sent, [])

    def test_missing_transcript_path_sends_notice(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        self.bro_out.handle({"session_id": "s1"}, self.state, sender=self._sender)
        self.assertEqual(self.sent, [(7, "（已完成，無文字輸出）")])

    def test_handle_flushes_pane_queue_before_reply(self):
        """#88：agent 這個 turn 結束時，Stop hook 要順手消化自己 pane 的 bro-queue，
        不能只做 Telegram 回覆這一半。"""
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
        ])
        calls = []
        self.bro_out.handle(
            {"session_id": "s1", "transcript_path": str(t)},
            self.state,
            sender=self._sender,
            queue_flush=lambda: calls.append(1),
        )
        self.assertEqual(calls, [1])

    def test_stop_hook_active_does_not_flush_queue(self):
        """既有的遞迴防呆（stop_hook_active）比消化佇列還早短路，維持原行為。"""
        calls = []
        self.bro_out.handle(
            {"session_id": "s1", "stop_hook_active": True},
            self.state,
            sender=self._sender,
            queue_flush=lambda: calls.append(1),
        )
        self.assertEqual(calls, [])

    def test_queue_flush_failure_is_logged_and_does_not_block_reply(self):
        """hook 規範：消化佇列失敗只能記 log，絕不能讓 Telegram 回覆跟著斷掉。"""
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
        ])
        logged = []
        orig_log = self.bro_out._log
        self.bro_out._log = lambda stage, exc: logged.append((stage, exc))
        try:
            sent = self.bro_out.handle(
                {"session_id": "s1", "transcript_path": str(t)},
                self.state,
                sender=self._sender,
                queue_flush=lambda: (_ for _ in ()).throw(RuntimeError("queue kaboom")),
            )
        finally:
            self.bro_out._log = orig_log
        self.assertTrue(sent)
        self.assertEqual(self.sent, [(7, "ok")])
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0][0], "queue_flush")

    def test_flush_pane_queue_noop_without_tmux_pane_env(self):
        calls = []
        orig_flush, orig_env = self.bro_out.bro_queue.flush, os.environ.pop("TMUX_PANE", None)
        self.bro_out.bro_queue.flush = lambda *a, **k: calls.append((a, k))
        try:
            self.bro_out._flush_pane_queue()
        finally:
            self.bro_out.bro_queue.flush = orig_flush
            if orig_env is not None:
                os.environ["TMUX_PANE"] = orig_env
        self.assertEqual(calls, [])

    def test_flush_pane_queue_uses_tmux_pane_env_as_target(self):
        calls = []
        orig_flush, orig_env = self.bro_out.bro_queue.flush, os.environ.get("TMUX_PANE")
        self.bro_out.bro_queue.flush = lambda pane_id, **k: calls.append((pane_id, k))
        os.environ["TMUX_PANE"] = "%42"
        try:
            self.bro_out._flush_pane_queue()
        finally:
            self.bro_out.bro_queue.flush = orig_flush
            if orig_env is None:
                os.environ.pop("TMUX_PANE", None)
            else:
                os.environ["TMUX_PANE"] = orig_env
        self.assertEqual(len(calls), 1)
        pane_id, kwargs = calls[0]
        self.assertEqual(pane_id, "%42")
        self.assertEqual(kwargs.get("max_attempts"), self.bro_out.QUEUE_FLUSH_MAX_ATTEMPTS)

    def test_stop_hook_end_to_end_delivers_message_queued_while_busy(self):
        """整合情境：agent 忙碌時排進佇列的訊息，在這個 turn 的 Stop hook 觸發後
        真的被消化掉（佇列清空）——對應 issue 要求的「queue 消化後真的送達」。"""
        from paulshaclaw.core import bro_queue

        with tempfile.TemporaryDirectory() as agents_root:
            old_root = os.environ.get("PSC_AGENTS_ROOT")
            os.environ["PSC_AGENTS_ROOT"] = agents_root
            try:
                bro_queue.enqueue("%9", "[bro:7] queued while busy")

                def fake_queue_flush():
                    bro_queue.flush(
                        "%9",
                        max_attempts=5,
                        send=lambda pane_id, message: True,
                        capture=lambda pane_id: "[bro:7] queued while busy",
                    )

                (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
                t = self._transcript([
                    {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}},
                ])
                self.bro_out.handle(
                    {"session_id": "s1", "transcript_path": str(t)},
                    self.state,
                    sender=self._sender,
                    queue_flush=fake_queue_flush,
                )

                self.assertEqual(bro_queue._read_entries(bro_queue.queue_file("%9")), [])
            finally:
                if old_root is None:
                    os.environ.pop("PSC_AGENTS_ROOT", None)
                else:
                    os.environ["PSC_AGENTS_ROOT"] = old_root

    def test_bridge_nonzero_exit_is_logged(self):
        import types

        logged = []
        fake_proc = types.SimpleNamespace(returncode=1, stderr="boom")
        orig_run, orig_log = self.bro_out.subprocess.run, self.bro_out._log
        self.bro_out.subprocess.run = lambda *a, **k: fake_proc
        self.bro_out._log = lambda stage, exc: logged.append((stage, str(exc)))
        try:
            self.bro_out._send_via_bridge(7, "hi")
        finally:
            self.bro_out.subprocess.run, self.bro_out._log = orig_run, orig_log
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0][0], "send")
        self.assertIn("boom", logged[0][1])


if __name__ == "__main__":
    unittest.main()
