from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "psc_bro_return", REPO / "scripts" / "gemma4-hooks" / "psc-bro-return.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class _Sender:
    def __init__(self):
        self.calls = []

    def __call__(self, user_id, text):
        self.calls.append((user_id, text))


class TurnScopedBindingTests(unittest.TestCase):
    def _run(self, prompts, reply):
        snd = _Sender()
        sent = mod.handle_resolved(prompts=prompts, reply=reply, sender=snd)
        return snd, sent

    def test_first_bro_then_local_no_send(self):
        snd, sent = self._run(["[bro:111] a", "local b"], "r")
        self.assertFalse(sent)
        self.assertEqual(snd.calls, [])

    def test_first_bro_then_different_user_sends_new(self):
        snd, sent = self._run(["[bro:111] a", "[bro:222] b"], "r")
        self.assertTrue(sent)
        self.assertEqual(snd.calls, [(222, "r")])

    def test_first_local_then_bro_sends_bro(self):
        snd, sent = self._run(["local a", "[bro:111] b"], "r")
        self.assertEqual(snd.calls, [(111, "r")])

    def test_no_marker_no_send(self):
        snd, sent = self._run(["local only"], "r")
        self.assertEqual(snd.calls, [])

    def test_reply_unreadable_skips_no_empty_notice(self):
        snd, sent = self._run(["[bro:111] a"], None)
        self.assertFalse(sent)
        self.assertEqual(snd.calls, [])

    def test_reply_empty_sends_empty_notice(self):
        snd, sent = self._run(["[bro:111] a"], "")
        self.assertEqual(snd.calls, [(111, mod.EMPTY_NOTICE)])


class PlatformResolveTests(unittest.TestCase):
    def test_copilot_uses_history(self):
        orig = mod.read_copilot_history
        mod.read_copilot_history = lambda root, sid: {
            "user_prompts": ["[bro:7] hi"], "assistant_summary": "yo"}
        try:
            prompts, reply = mod.resolve("copilot", {"session_id": "s1"})
        finally:
            mod.read_copilot_history = orig
        self.assertEqual(prompts[-1], "[bro:7] hi")
        self.assertEqual(reply, "yo")

    def test_copilot_accepts_camelcase_session_id(self):
        # adversarial finding：copilot agentStop payload 用 camelCase sessionId
        captured = {}
        orig = mod.read_copilot_history

        def fake(root, sid):
            captured["sid"] = sid
            return {"user_prompts": ["[bro:9] hi"], "assistant_summary": "ok"}

        mod.read_copilot_history = fake
        try:
            prompts, reply = mod.resolve("copilot", {"sessionId": "cop-1"})
        finally:
            mod.read_copilot_history = orig
        self.assertEqual(captured["sid"], "cop-1")
        self.assertEqual(reply, "ok")

    def test_codex_reply_from_payload_missing_key_is_none(self):
        orig = mod.read_codex_rollout
        mod.read_codex_rollout = lambda p: {"user_prompts": ["[bro:7] hi"]}
        try:
            prompts, reply = mod.resolve("codex", {"transcript_path": "/x"})
        finally:
            mod.read_codex_rollout = orig
        self.assertEqual(prompts[-1], "[bro:7] hi")
        self.assertIsNone(reply)

    def test_codex_non_string_reply_is_none(self):
        orig = mod.read_codex_rollout
        mod.read_codex_rollout = lambda p: {"user_prompts": ["[bro:7] hi"]}
        try:
            _, reply = mod.resolve("codex", {"last_assistant_message": 42, "transcript_path": "/x"})
        finally:
            mod.read_codex_rollout = orig
        self.assertIsNone(reply)

    def test_handle_end_to_end_codex(self):
        snd = _Sender()
        orig = mod.read_codex_rollout
        mod.read_codex_rollout = lambda p: {"user_prompts": ["[bro:7] hi"]}
        try:
            mod.handle({"last_assistant_message": "hi", "transcript_path": "/x"}, "codex", sender=snd)
        finally:
            mod.read_codex_rollout = orig
        self.assertEqual(snd.calls, [(7, "hi")])


if __name__ == "__main__":
    unittest.main()
