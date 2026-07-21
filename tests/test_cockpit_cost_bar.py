from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from paulshaclaw.cost.models import CostSnapshot, ProviderSnapshot, UsageWindow


def _cc_snapshot() -> CostSnapshot:
    return CostSnapshot(
        generated_at=datetime(2026, 7, 21, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
        cache_status="fresh",
        providers={
            "cc": ProviderSnapshot(
                source_status="ok",
                windows={
                    "five_hour": UsageWindow(used_percent=21, reset_at=None, display_reset="22:20"),
                    "weekly": UsageWindow(used_percent=57, reset_at=None, display_reset="6d"),
                },
            )
        },
    )


class AnsiClipTests(unittest.TestCase):
    def test_clip_truncates_visible_chars_keeping_ansi_and_resets(self) -> None:
        from paulshaclaw.cockpit.cost_bar import _ansi_clip

        s = "\033[38;5;33mHELLO\033[0m WORLD"  # 可見 "HELLO WORLD"（11）
        self.assertEqual(_ansi_clip(s, 5), "\033[38;5;33mHELLO\033[0m")

    def test_clip_noop_when_within_width(self) -> None:
        from paulshaclaw.cockpit.cost_bar import _ansi_clip

        s = "\033[38;5;33mHI\033[0m"
        self.assertEqual(_ansi_clip(s, 10), s)


class CostLineTests(unittest.TestCase):
    def test_cost_line_none_when_snapshot_unavailable(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        with patch.object(cost_bar, "read_snapshot", return_value=None):
            self.assertIsNone(cost_bar.cost_line(80))

    def test_cost_line_formats_ansi_and_contains_percent(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        with patch.object(cost_bar, "read_snapshot", return_value=_cc_snapshot()):
            line = cost_bar.cost_line(200)

        self.assertIsNotNone(line)
        assert line is not None
        self.assertIn("21%", line)
        self.assertIn("\033[", line)   # ANSI fg
        self.assertNotIn("#[", line)   # 無 tmux 碼
        self.assertNotIn("bg=", line)  # 無背景色

    def test_read_snapshot_is_fail_soft(self) -> None:
        # read_snapshot 遇任何錯誤都回 None，絕不 raise（不擋 TUI 啟動）。
        from paulshaclaw.cockpit import cost_bar

        with patch("paulshaclaw.cockpit.cost_bar.load_cost_config", side_effect=RuntimeError("boom")):
            self.assertIsNone(cost_bar.read_snapshot())


if __name__ == "__main__":
    unittest.main()
