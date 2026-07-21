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


def _full_snapshot() -> CostSnapshot:
    from paulshaclaw.cost.models import CopilotAccountUsage

    return CostSnapshot(
        generated_at=datetime(2026, 7, 21, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
        cache_status="fresh",
        providers={
            "cdx": ProviderSnapshot(
                source_status="estimated",
                windows={
                    "five_hour": UsageWindow(used_percent=80, reset_at=None, display_reset="6d"),
                    "weekly": UsageWindow(used_percent=None, reset_at=None, display_reset=None),
                },
            ),
            "cc": ProviderSnapshot(
                source_status="ok",
                windows={
                    "five_hour": UsageWindow(used_percent=3, reset_at=None, display_reset="03:20"),
                    "weekly": UsageWindow(used_percent=57, reset_at=None, display_reset="6d"),
                },
            ),
            "cpt": ProviderSnapshot(
                source_status="ok",
                accounts=(
                    CopilotAccountUsage(
                        account_id="h", label="haman", kind="individual",
                        used_requests=None, monthly_allowance=None, source="http",
                        percent_used=92,
                    ),
                ),
            ),
        },
    )


class CostSplitTests(unittest.TestCase):
    def test_split_returns_cdx_suffix_and_cc_cpt_rest(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        with patch.object(cost_bar, "read_snapshot", return_value=_full_snapshot()):
            net_suffix, rest = cost_bar.cost_split(cost_width=90, net_width=20)

        self.assertIsNotNone(net_suffix)
        assert net_suffix is not None
        self.assertIn("cdx", net_suffix)
        self.assertIn("|", net_suffix)   # 前導分隔符
        self.assertNotIn("cc ", net_suffix)

        self.assertIsNotNone(rest)
        assert rest is not None
        self.assertIn("cc ", rest)
        self.assertIn("cpt: ", rest)
        self.assertIn("92%", rest)
        self.assertNotIn("cdx", rest)

    def test_split_none_when_no_snapshot(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        with patch.object(cost_bar, "read_snapshot", return_value=None):
            self.assertEqual(cost_bar.cost_split(90, 20), (None, None))
