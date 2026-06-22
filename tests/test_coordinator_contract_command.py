from __future__ import annotations

import shlex
import unittest

from paulshaclaw.coordinator.contract_command import (
    DEFAULT_EXECUTOR,
    build_dispatch_command,
)


class BuildDispatchCommandTests(unittest.TestCase):
    def test_carries_contract_task_and_plan(self) -> None:
        cmd = build_dispatch_command(
            "builder", task="persona-phase-a", plan_path="docs/superpowers/plans/p.md"
        )
        self.assertIn("[PERSONA CONTRACT", cmd)
        self.assertIn("role: builder", cmd)
        self.assertIn("persona-phase-a", cmd)
        self.assertIn("docs/superpowers/plans/p.md", cmd)
        self.assertIn("copilot", cmd)

    def test_prompt_is_single_shlex_token(self) -> None:
        cmd = build_dispatch_command("builder", task="t", plan_path="p.md")
        parts = shlex.split(cmd)
        self.assertEqual(parts[: len(DEFAULT_EXECUTOR)], list(DEFAULT_EXECUTOR))
        self.assertEqual(len(parts), len(DEFAULT_EXECUTOR) + 1)

    def test_unknown_role_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_dispatch_command("nobody", task="t", plan_path="p.md")

    def test_is_pure_no_file_read(self) -> None:
        cmd = build_dispatch_command("builder", task="t", plan_path="/nope/x.md")
        self.assertIn("/nope/x.md", cmd)


if __name__ == "__main__":
    unittest.main()
