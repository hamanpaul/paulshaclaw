from __future__ import annotations

import unittest

from paulshaclaw.coordinator.cli import _resolve_launcher
from paulshaclaw.coordinator.launcher import SubprocessLauncher


class ResolveLauncherTests(unittest.TestCase):
    def test_builds_subprocess_launcher_with_flags(self) -> None:
        lr = _resolve_launcher("copilot", None, allow_unsafe=True, model="haiku-4.5")
        self.assertIsInstance(lr, SubprocessLauncher)
        self.assertTrue(lr._allow_unsafe)
        self.assertEqual(lr._model, "haiku-4.5")
        self.assertEqual(lr._executor, "copilot")

    def test_respects_injected_launcher(self) -> None:
        sentinel = object()
        self.assertIs(_resolve_launcher("copilot", sentinel, allow_unsafe=True, model="x"), sentinel)

    def test_none_executor_returns_none(self) -> None:
        self.assertIsNone(_resolve_launcher(None, None, allow_unsafe=False, model=None))


if __name__ == "__main__":
    unittest.main()
