from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from paulshaclaw.cost.config import CostConfig, load_cost_config
from paulshaclaw.cost.formatter import classify_usage, format_footer
from paulshaclaw.cost.models import (
    CopilotAccountUsage,
    CostSnapshot,
    ProviderSnapshot,
    UsageWindow,
)
from paulshaclaw.cost.providers import collect_all, collect_codex, collect_copilot


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

    def test_footer_uses_tmux_style_by_default(self) -> None:
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
                            used_percent=91,
                            reset_at=datetime(2026, 5, 2, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="3d",
                        ),
                    },
                ),
                "cc": ProviderSnapshot(source_status="unknown", windows={}),
                "cpt": ProviderSnapshot(
                    source_status="fresh",
                    accounts=(
                        CopilotAccountUsage("hamanpaul", "haman", "personal", 1200, 1500, "github_user_billing"),
                    ),
                ),
            },
        )

        footer = format_footer(snapshot)

        self.assertIn("#[fg=green]18%(15:21)#[default]", footer)
        self.assertIn("#[fg=red]91%(3d)#[default]", footer)
        self.assertIn("#[fg=colour245]--#[default]", footer)
        self.assertIn("#[fg=yellow]haman:1200#[default]", footer)

    def test_footer_omits_empty_copilot_provider(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(source_status="fresh", windows={}),
                "cpt": ProviderSnapshot(source_status="fresh", accounts=()),
            },
        )

        footer = format_footer(snapshot, use_tmux_style=False)

        self.assertNotIn("cpt", footer)
        self.assertEqual(footer, "cdx 5h:-- wk:--")

    def test_threshold_boundaries(self) -> None:
        self.assertEqual(classify_usage(69), "low")
        self.assertEqual(classify_usage(70), "warning")
        self.assertEqual(classify_usage(89), "warning")
        self.assertEqual(classify_usage(90), "critical")
        self.assertEqual(classify_usage(None), "neutral")


class Stage8ConfigProviderTests(unittest.TestCase):
    def write_config(self, body: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        try:
            handle.write(textwrap.dedent(body))
            handle.flush()
        finally:
            handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_cost_config_defaults(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertIsInstance(cfg, CostConfig)
        self.assertEqual(cfg.timezone, "Asia/Taipei")
        self.assertEqual(cfg.cache_ttl_seconds, 120)
        self.assertEqual(cfg.tmux_refresh_seconds, 30)
        self.assertEqual(cfg.warning_percent, 70)
        self.assertEqual(cfg.critical_percent, 90)
        self.assertEqual(cfg.copilot_accounts, ())

    def test_copilot_accounts_are_config_driven(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: company-user
                      label: work
                      kind: company
                      monthly_allowance: 300
                      org: acme
                    - id: personal-user
                      label: me
                      kind: personal
                      monthly_allowance: 1500
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertEqual([account.label for account in cfg.copilot_accounts], ["work", "me"])
        self.assertEqual(cfg.copilot_accounts[0].account_id, "company-user")
        self.assertEqual(cfg.copilot_accounts[0].org, "acme")

    def test_copilot_account_defaults_label_and_kind(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: default-user
                      monthly_allowance: 1500
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertEqual(len(cfg.copilot_accounts), 1)
        self.assertEqual(cfg.copilot_accounts[0].account_id, "default-user")
        self.assertEqual(cfg.copilot_accounts[0].label, "default-user")
        self.assertEqual(cfg.copilot_accounts[0].kind, "personal")

    def test_collect_copilot_uses_injected_fetcher_before_local_fallback(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: hamanpaul
                      label: haman
                      kind: personal
                      monthly_allowance: 1500
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            return 724, "github_user_billing"

        provider = collect_copilot(cfg, fetcher=fetcher)

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.accounts[0].label, "haman")
        self.assertEqual(provider.accounts[0].used_requests, 724)
        self.assertEqual(provider.accounts[0].source, "github_user_billing")

    def test_collect_copilot_marks_local_observed_fallback(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: local-user
                      label: local
                      kind: personal
                      monthly_allowance: 100
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            raise RuntimeError("network unavailable")

        provider = collect_copilot(
            cfg,
            fetcher=fetcher,
            local_observed={"local-user": 12},
        )

        self.assertEqual(provider.source_status, "stale")
        self.assertEqual(provider.accounts[0].source, "local_observed")
        self.assertEqual(provider.accounts[0].used_requests, 12)

    def test_collect_copilot_keeps_fresh_status_when_other_accounts_are_unknown(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: fresh-user
                      label: fresh
                    - id: unknown-user
                      label: unknown
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            if account.account_id == "fresh-user":
                return 724, "github_user_billing"
            raise RuntimeError("network unavailable")

        provider = collect_copilot(cfg, fetcher=fetcher)

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.accounts[0].source, "github_user_billing")
        self.assertEqual(provider.accounts[1].source, "unknown")

    def test_collect_copilot_keeps_stale_status_when_other_accounts_are_unknown(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: local-user
                      label: local
                    - id: unknown-user
                      label: unknown
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            raise RuntimeError("network unavailable")

        provider = collect_copilot(
            cfg,
            fetcher=fetcher,
            local_observed={"local-user": 12},
        )

        self.assertEqual(provider.source_status, "stale")
        self.assertEqual(provider.accounts[0].source, "local_observed")
        self.assertEqual(provider.accounts[1].source, "unknown")

    def test_collect_copilot_prefers_fresh_over_stale_and_unknown(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: fresh-user
                      label: fresh
                    - id: local-user
                      label: local
                    - id: unknown-user
                      label: unknown
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            if account.account_id == "fresh-user":
                return 724, "github_user_billing"
            raise RuntimeError("network unavailable")

        provider = collect_copilot(
            cfg,
            fetcher=fetcher,
            local_observed={"local-user": 12},
        )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(
            [account.source for account in provider.accounts],
            ["github_user_billing", "local_observed", "unknown"],
        )

    def test_collect_all_omits_copilot_when_no_accounts_are_configured(self) -> None:
        cfg = CostConfig()

        providers = collect_all(cfg)

        self.assertEqual(set(providers), {"cdx", "cc"})

    def test_collect_all_includes_copilot_when_accounts_are_configured(self) -> None:
        cfg = CostConfig(
            copilot_accounts=(
                load_cost_config(
                    config_path=self.write_config(
                        """
                        workspaces:
                          - path: /tmp/ws
                            name: ws
                        cost:
                          providers:
                            copilot:
                              accounts:
                                - id: fresh-user
                                  label: fresh
                        """
                    )
                ).copilot_accounts[0],
            )
        )

        providers = collect_all(cfg)

        self.assertEqual(set(providers), {"cdx", "cc", "cpt"})
        self.assertEqual(providers["cpt"].accounts[0].account_id, "fresh-user")

    def test_collect_codex_does_not_estimate_missing_quota_windows(self) -> None:
        provider = collect_codex()

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})
