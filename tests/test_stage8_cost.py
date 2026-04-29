from __future__ import annotations

import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from paulshaclaw.cost.formatter import classify_usage, format_footer
from paulshaclaw.cost.models import (
    CopilotAccountUsage,
    CostSnapshot,
    ProviderSnapshot,
    UsageWindow,
)


class Stage8ModelFormatterTests(unittest.TestCase):
    def test_snapshot_serializes_provider_neutral_json(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(
                    source_status="fresh",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=18,
                            reset_at=datetime(2026, 4, 29, 15, 21, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="15:21",
                        ),
                        "weekly": UsageWindow(
                            used_percent=41,
                            reset_at=datetime(2026, 5, 2, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="3d",
                        ),
                    },
                ),
                "cc": ProviderSnapshot(source_status="unknown", windows={}),
                "cpt": ProviderSnapshot(
                    source_status="fresh",
                    accounts=(
                        CopilotAccountUsage(
                            account_id="hamanpaul",
                            label="haman",
                            kind="personal",
                            used_requests=724,
                            monthly_allowance=1500,
                            source="github_user_billing",
                        ),
                    ),
                ),
            },
        )

        payload = snapshot.to_jsonable()
        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["timezone"], "Asia/Taipei")
        self.assertEqual(decoded["providers"]["cdx"]["windows"]["five_hour"]["display_reset"], "15:21")
        self.assertEqual(decoded["providers"]["cpt"]["accounts"][0]["label"], "haman")

    def test_footer_renders_balanced_format(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(
                    source_status="fresh",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=18,
                            reset_at=datetime(2026, 4, 29, 15, 21, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="15:21",
                        ),
                        "weekly": UsageWindow(
                            used_percent=41,
                            reset_at=datetime(2026, 5, 2, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="3d",
                        ),
                    },
                ),
                "cc": ProviderSnapshot(source_status="unknown", windows={}),
                "cpt": ProviderSnapshot(
                    source_status="fresh",
                    accounts=(
                        CopilotAccountUsage("hamanpaul", "haman", "personal", 724, 1500, "github_user_billing"),
                        CopilotAccountUsage("paulc-arc", "arc", "company", 127, 300, "github_org_billing"),
                    ),
                ),
            },
        )

        footer = format_footer(snapshot, use_tmux_style=False)

        self.assertIn("cdx 5h:18%(15:21) wk:41%(3d)", footer)
        self.assertIn("cc 5h:-- wk:--", footer)
        self.assertIn("cpt haman:724 arc:127", footer)

    def test_footer_marks_stale_provider(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="stale",
            providers={"cdx": ProviderSnapshot(source_status="stale", windows={})},
        )

        self.assertIn("cdx~", format_footer(snapshot, use_tmux_style=False))

    def test_threshold_boundaries(self) -> None:
        self.assertEqual(classify_usage(69), "low")
        self.assertEqual(classify_usage(70), "warning")
        self.assertEqual(classify_usage(89), "warning")
        self.assertEqual(classify_usage(90), "critical")
        self.assertEqual(classify_usage(None), "neutral")
