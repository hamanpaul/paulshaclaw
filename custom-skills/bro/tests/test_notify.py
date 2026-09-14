from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notify.py"
SPEC = importlib.util.spec_from_file_location("notify", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
notify_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = notify_mod
SPEC.loader.exec_module(notify_mod)


class _FakeBridge:
    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self.fail = fail

    def send_reply(self, *, text, source_user_id=None):
        self.calls.append({"text": text, "source_user_id": source_user_id})
        if self.fail:
            raise RuntimeError("bridge down")
        return []


class NotifyPathSelectionTest(unittest.TestCase):
    def test_gateway_first_when_up_and_send_ok(self):
        bridge = _FakeBridge()
        path = notify_mod.notify(
            "hello",
            reply_bridge=bridge,
            gateway_probe=lambda: True,
            gateway_sender=lambda text: True,
        )
        self.assertEqual(path, "gateway")
        self.assertEqual(bridge.calls, [])  # direct not touched

    def test_fallback_to_direct_when_gateway_down(self):
        bridge = _FakeBridge()
        path = notify_mod.notify(
            "hello",
            reply_bridge=bridge,
            gateway_probe=lambda: False,
            gateway_sender=lambda text: (_ for _ in ()).throw(AssertionError("must not send")),
        )
        self.assertEqual(path, "direct")
        self.assertEqual(len(bridge.calls), 1)
        self.assertEqual(bridge.calls[0]["text"], "hello")

    def test_fallback_to_direct_when_gateway_send_fails(self):
        bridge = _FakeBridge()
        path = notify_mod.notify(
            "hello",
            reply_bridge=bridge,
            gateway_probe=lambda: True,
            gateway_sender=lambda text: False,
        )
        self.assertEqual(path, "direct")
        self.assertEqual(len(bridge.calls), 1)

    def test_no_gateway_flag_forces_direct(self):
        bridge = _FakeBridge()
        path = notify_mod.notify(
            "hello",
            use_gateway=False,
            reply_bridge=bridge,
            gateway_probe=lambda: (_ for _ in ()).throw(AssertionError("probe must not run")),
        )
        self.assertEqual(path, "direct")

    def test_source_user_id_threaded_to_bridge(self):
        bridge = _FakeBridge()
        notify_mod.notify(
            "hello",
            source_user_id=8313353234,
            reply_bridge=bridge,
            gateway_probe=lambda: False,
        )
        self.assertEqual(bridge.calls[0]["source_user_id"], 8313353234)

    def test_all_paths_fail_raises(self):
        bridge = _FakeBridge(fail=True)
        with self.assertRaises(RuntimeError):
            notify_mod.notify(
                "hello",
                reply_bridge=bridge,
                gateway_probe=lambda: False,
            )

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            notify_mod.notify("   ", reply_bridge=_FakeBridge())

    def test_dry_run_sends_nothing(self):
        bridge = _FakeBridge()
        path = notify_mod.notify(
            "hello",
            dry_run=True,
            reply_bridge=bridge,
            gateway_probe=lambda: (_ for _ in ()).throw(AssertionError("no probe on dry-run")),
        )
        self.assertEqual(path, "dry-run")
        self.assertEqual(bridge.calls, [])


class GatewayHelpersTest(unittest.TestCase):
    def test_send_via_gateway_success(self):
        class _Resp:
            status = 200

            def read(self):
                return b'{"ok":true}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(notify_mod, "MAX_API_TOKEN_PATH") as tok:
            tok.read_text.return_value = "secret-token"
            ok = notify_mod.send_via_gateway("hi", opener=lambda req, timeout: _Resp())
        self.assertTrue(ok)

    def test_send_via_gateway_missing_token(self):
        with mock.patch.object(notify_mod, "MAX_API_TOKEN_PATH") as tok:
            tok.read_text.side_effect = OSError("no token")
            ok = notify_mod.send_via_gateway("hi", opener=lambda req, timeout: None)
        self.assertFalse(ok)

    def test_send_via_gateway_non_ok_body(self):
        class _Resp:
            status = 200

            def read(self):
                return b'{"ok":false,"error":"nope"}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(notify_mod, "MAX_API_TOKEN_PATH") as tok:
            tok.read_text.return_value = "secret-token"
            ok = notify_mod.send_via_gateway("hi", opener=lambda req, timeout: _Resp())
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
