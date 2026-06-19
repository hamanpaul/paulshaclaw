import importlib.util
import json
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
