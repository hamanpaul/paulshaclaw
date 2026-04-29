from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from paulshaclaw.cost.cache import (
    SnapshotCache,
    build_snapshot,
    load_snapshot_payload,
)
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


class Stage8CacheTests(unittest.TestCase):
    def test_invalid_timezone_falls_back_to_taipei(self) -> None:
        snapshot = build_snapshot(
            timezone=None,
            providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
        )

        self.assertEqual(snapshot.timezone, "Asia/Taipei")
        self.assertEqual(snapshot.generated_at.tzinfo, ZoneInfo("Asia/Taipei"))

    def test_fresh_cache_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
            )
            cache.write(snapshot)

            loaded = cache.read_if_fresh()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.timezone, "Asia/Taipei")

    def test_stale_cache_returns_none_for_fresh_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=0)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
            )
            cache.write(snapshot)

            self.assertIsNone(cache.read_if_fresh())

    def test_lock_busy_reads_old_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="stale", windows={})},
            )
            cache.write(snapshot)
            cache.lock_path.write_text("busy", encoding="utf-8")

            loaded = cache.read_stale()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.providers["cdx"].source_status, "stale")

    def test_lock_yields_true_and_removes_file_after_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)

            with cache.lock() as acquired:
                self.assertTrue(acquired)
                self.assertTrue(cache.lock_path.exists())

            self.assertFalse(cache.lock_path.exists())

    def test_lock_contention_yields_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)
            cache.lock_path.parent.mkdir(parents=True, exist_ok=True)
            cache.lock_path.write_text("busy", encoding="utf-8")

            with cache.lock() as acquired:
                self.assertFalse(acquired)

    def test_cache_write_uses_pretty_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
            )

            cache.write(snapshot)

            content = cache.snapshot_path.read_text(encoding="utf-8")
            self.assertIn('\n  "generated_at"', content)
            self.assertTrue(content.endswith("\n"))

    def test_load_snapshot_payload_keeps_benign_note(self) -> None:
        payload = {
            "generated_at": "2026-04-29T15:00:00+08:00",
            "timezone": "Asia/Taipei",
            "cache_status": "fresh",
            "providers": {
                "cc": {
                    "source_status": "unknown",
                    "note": "missing credentials",
                }
            },
        }

        snapshot = load_snapshot_payload(payload)

        self.assertEqual(snapshot.providers["cc"].note, "missing credentials")

    def test_load_snapshot_payload_preserves_string_note_without_filtering(self) -> None:
        payload = {
            "generated_at": "2026-04-29T15:00:00+08:00",
            "timezone": "Asia/Taipei",
            "cache_status": "fresh",
            "providers": {
                "cc": {
                    "source_status": "unknown",
                    "note": "ghp_xxx",
                }
            },
        }

        snapshot = load_snapshot_payload(payload)

        self.assertEqual(snapshot.providers["cc"].note, "ghp_xxx")


class Stage8CliTests(unittest.TestCase):
    def test_once_cli_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "paulshaclaw.yaml"
            config.write_text(
                textwrap.dedent(
                    """
                    workspaces:
                      - path: /tmp/ws
                        name: ws
                    cost:
                      cache_dir: {cache_dir}
                    """
                ).format(cache_dir=str(Path(tmpdir) / "cache")),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, "-m", "paulshaclaw.cost", "--once", "--config", str(config)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("providers", payload)

    def test_status_cli_prints_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "paulshaclaw.yaml"
            config.write_text(
                textwrap.dedent(
                    """
                    workspaces:
                      - path: /tmp/ws
                        name: ws
                    cost:
                      cache_dir: {cache_dir}
                      providers:
                        copilot:
                          accounts:
                            - id: hamanpaul
                              label: haman
                              kind: personal
                              monthly_allowance: 1500
                    """
                ).format(cache_dir=str(Path(tmpdir) / "cache")),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, "-m", "paulshaclaw.cost.status", "--config", str(config)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(len(completed.stdout.splitlines()), 1)
            self.assertIn("cdx", completed.stdout)
