from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from collections.abc import Mapping
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from paulshaclaw.cost import __main__ as cost_cli
from paulshaclaw.cost import status as cost_status_cli
from paulshaclaw.cost.cache import (
    SnapshotCache,
    build_snapshot,
    load_snapshot_payload,
)
from paulshaclaw.cost import config as cost_config_module
from paulshaclaw.cost.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    CostConfig,
    load_cost_config,
)
from paulshaclaw.cost.formatter import classify_usage, format_footer
from paulshaclaw.cost.models import (
    CopilotAccountUsage,
    CostSnapshot,
    ProviderSnapshot,
    UsageWindow,
)
from paulshaclaw.cost.providers import (
    _claude_message_token_total,
    _read_local_observed_total,
    collect_all,
    collect_claude,
    collect_codex,
    collect_copilot,
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

    def test_footer_marks_estimated_provider_with_question_suffix(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cc": ProviderSnapshot(
                    source_status="estimated",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=35,
                            reset_at=None,
                            display_reset="2h",
                        ),
                    },
                )
            },
        )

        footer = format_footer(snapshot, use_tmux_style=False)

        self.assertIn("cc? 5h:35%(2h) wk:--", footer)

    def test_footer_uses_estimated_tmux_style(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(
                    source_status="estimated",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=91,
                            reset_at=None,
                            display_reset="1h",
                        ),
                    },
                )
            },
        )

        footer = format_footer(snapshot)

        self.assertIn("cdx?", footer)
        self.assertIn("#[fg=magenta]91%(1h)#[default]", footer)
        self.assertNotIn("#[fg=red]91%(1h)#[default]", footer)

    def test_footer_uses_estimated_tmux_style_for_copilot_account(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cpt": ProviderSnapshot(
                    source_status="estimated",
                    accounts=(
                        CopilotAccountUsage(
                            "hamanpaul",
                            "haman",
                            "personal",
                            724,
                            1500,
                            "local_observed",
                        ),
                    ),
                ),
            },
        )

        footer = format_footer(snapshot)

        self.assertIn("cpt?", footer)
        self.assertIn("#[fg=magenta]haman:724#[default]", footer)
        self.assertNotIn("#[fg=green]haman:724#[default]", footer)

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

    def scratch_tempdir(self) -> tempfile.TemporaryDirectory[str]:
        scratch_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        scratch_root.mkdir(exist_ok=True)
        env_tmpdir = os.environ.get("TMPDIR")

        def cleanup_scratch_root() -> None:
            with contextlib.suppress(OSError):
                scratch_root.rmdir()

        if not env_tmpdir or Path(env_tmpdir).resolve() != scratch_root.resolve():
            self.addCleanup(cleanup_scratch_root)
        return tempfile.TemporaryDirectory(dir=scratch_root)

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

    def test_cost_config_uses_builtin_defaults_when_runtime_config_missing(self) -> None:
        with (
            patch.object(cost_config_module, "DEFAULT_CONFIG_PATH", Path("missing-cost-config.yaml")),
            patch.dict("os.environ", {}, clear=True),
        ):
            cfg = load_cost_config()

        self.assertEqual(cfg.timezone, "Asia/Taipei")
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

    def test_claude_and_codex_provider_config_are_parsed(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                claude:
                  statusline_sidecar: /tmp/claude-rate.json
                  max_age_seconds: 90
                  local_fallback: true
                codex:
                  enabled: true
                  auth_path: /tmp/codex-auth.json
                  usage_url: https://chatgpt.com/api/codex/usage
                  max_age_seconds: 45
                  local_fallback: true
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertEqual(cfg.claude.statusline_sidecar, Path("/tmp/claude-rate.json"))
        self.assertEqual(cfg.claude.max_age_seconds, 90)
        self.assertTrue(cfg.claude.local_fallback)
        self.assertTrue(cfg.codex.enabled)
        self.assertEqual(cfg.codex.auth_path, Path("/tmp/codex-auth.json"))
        self.assertEqual(cfg.codex.usage_url, "https://chatgpt.com/api/codex/usage")
        self.assertEqual(cfg.codex.max_age_seconds, 45)
        self.assertTrue(cfg.codex.local_fallback)

    def test_claude_and_codex_provider_config_defaults_are_safe(self) -> None:
        cfg = CostConfig()

        self.assertIsInstance(cfg.claude, ClaudeProviderConfig)
        self.assertIsInstance(cfg.codex, CodexProviderConfig)
        self.assertEqual(
            cfg.claude.statusline_sidecar,
            Path("~/.agents/state/cost/claude_rate_limits.json").expanduser(),
        )
        self.assertTrue(cfg.codex.enabled)
        self.assertEqual(cfg.codex.auth_path, Path("~/.codex/auth.json").expanduser())

    def test_load_cost_config_defaults_provider_sections_when_omitted(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts: []
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertIsInstance(cfg.claude, ClaudeProviderConfig)
        self.assertIsInstance(cfg.codex, CodexProviderConfig)
        self.assertEqual(
            cfg.claude.statusline_sidecar,
            Path("~/.agents/state/cost/claude_rate_limits.json").expanduser(),
        )
        self.assertEqual(cfg.claude.max_age_seconds, 300)
        self.assertFalse(cfg.claude.local_fallback)
        self.assertTrue(cfg.codex.enabled)
        self.assertEqual(cfg.codex.auth_path, Path("~/.codex/auth.json").expanduser())
        self.assertEqual(cfg.codex.usage_url, "https://chatgpt.com/api/codex/usage")
        self.assertEqual(cfg.codex.max_age_seconds, 300)
        self.assertFalse(cfg.codex.local_fallback)

    def test_claude_and_codex_provider_config_parse_string_booleans(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                claude:
                  local_fallback: "yes"
                codex:
                  enabled: "false"
                  local_fallback: "off"
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertTrue(cfg.claude.local_fallback)
        self.assertFalse(cfg.codex.enabled)
        self.assertFalse(cfg.codex.local_fallback)

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

    def test_collect_copilot_marks_local_observed_provider_estimated(self) -> None:
        cfg = CostConfig(
            copilot_accounts=(
                cost_config_module.CopilotAccountConfig(
                    account_id="local-user",
                    label="local",
                    kind="personal",
                    monthly_allowance=100,
                ),
            )
        )

        def fetcher(account):
            raise RuntimeError("network unavailable")

        provider = collect_copilot(
            cfg,
            fetcher=fetcher,
            local_observed={"local-user": 12},
        )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.accounts[0].source, "local_observed")

    def test_collect_copilot_fetches_runtime_personal_usage_without_injected_fetcher(self) -> None:
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

        with (
            patch("paulshaclaw.cost.providers._get_github_token", return_value="secret-token") as token_mock,
            patch(
                "paulshaclaw.cost.providers._fetch_json",
                return_value={"usageItems": [{"grossQuantity": 724}]},
            ) as fetch_mock,
            patch("paulshaclaw.cost.providers._collect_local_observed_usage", return_value={}) as local_mock,
        ):
            provider = collect_copilot(cfg)

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.accounts[0].used_requests, 724)
        self.assertEqual(provider.accounts[0].source, "github_user_billing")
        token_mock.assert_called_once_with("hamanpaul")
        local_mock.assert_not_called()
        request_url = fetch_mock.call_args.args[0]
        request_headers = fetch_mock.call_args.args[1]
        self.assertIn("/users/hamanpaul/settings/billing/premium_request/usage", request_url)
        self.assertIn("year=", request_url)
        self.assertIn("month=", request_url)
        self.assertEqual(request_headers["Authorization"], "Bearer secret-token")

    def test_collect_copilot_fetches_runtime_enterprise_usage_without_injected_fetcher(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: paulc-arc
                      label: arc
                      kind: company
                      monthly_allowance: 300
                      enterprise: acme-ent
            """
        )
        cfg = load_cost_config(config_path=path)

        with (
            patch("paulshaclaw.cost.providers._get_github_token", return_value="secret-token") as token_mock,
            patch(
                "paulshaclaw.cost.providers._fetch_json",
                return_value={"usageItems": [{"netQuantity": 127}]},
            ) as fetch_mock,
        ):
            provider = collect_copilot(cfg)

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.accounts[0].used_requests, 127)
        self.assertEqual(provider.accounts[0].source, "github_enterprise_billing")
        token_mock.assert_called_once_with("paulc-arc")
        request_url = fetch_mock.call_args.args[0]
        self.assertIn("/enterprises/acme-ent/settings/billing/premium_request/usage", request_url)
        self.assertIn("user=paulc-arc", request_url)

    def test_collect_copilot_runtime_does_not_use_unattributed_local_history(self) -> None:
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

        with (
            patch("paulshaclaw.cost.providers._fetch_account_usage", side_effect=RuntimeError("offline")),
            patch(
                "paulshaclaw.cost.providers._collect_local_observed_usage",
                return_value={"hamanpaul": 12},
            ) as local_mock,
        ):
            provider = collect_copilot(cfg)

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.accounts[0].source, "unknown")
        self.assertIsNone(provider.accounts[0].used_requests)
        local_mock.assert_not_called()

    def test_read_local_observed_total_counts_current_month_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / ".copilot" / "session-state" / "s1"
            root.mkdir(parents=True)
            (root / "events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session.shutdown",
                                "timestamp": "2026-04-30T23:59:00Z",
                                "data": {"totalPremiumRequests": 99},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "session.shutdown",
                                "timestamp": "2026-05-01T00:01:00Z",
                                "data": {"totalPremiumRequests": 5},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "session.shutdown",
                                "timestamp": "2026-05-20T12:00:00Z",
                                "data": {"totalPremiumRequests": 7},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("paulshaclaw.cost.providers.Path.home", return_value=Path(tmpdir)):
                total = _read_local_observed_total(year=2026, month=5)

        self.assertEqual(total, 12)

    def test_read_local_observed_total_ignores_timestamp_less_shutdowns_with_explicit_month(self) -> None:
        with self.scratch_tempdir() as tmpdir:
            root = Path(tmpdir) / ".copilot" / "session-state" / "s1"
            root.mkdir(parents=True)
            (root / "events.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session.shutdown",
                        "data": {"totalPremiumRequests": 12},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("paulshaclaw.cost.providers.Path.home", return_value=Path(tmpdir)):
                total = _read_local_observed_total(year=2026, month=5)

        self.assertEqual(total, 0)

    def test_read_local_observed_total_counts_timestamp_less_shutdowns_without_explicit_filter(self) -> None:
        with self.scratch_tempdir() as tmpdir:
            root = Path(tmpdir) / ".copilot" / "session-state" / "s1"
            root.mkdir(parents=True)
            (root / "events.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session.shutdown",
                        "data": {"totalPremiumRequests": 12},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("paulshaclaw.cost.providers.Path.home", return_value=Path(tmpdir)):
                total = _read_local_observed_total()

        self.assertEqual(total, 12)

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

    def test_collect_copilot_keeps_estimated_status_when_other_accounts_are_unknown(self) -> None:
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

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.accounts[0].source, "local_observed")
        self.assertEqual(provider.accounts[1].source, "unknown")

    def test_collect_copilot_prefers_fresh_over_estimated_and_unknown(self) -> None:
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

    def test_collect_codex_parses_quota_payload(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 23,
                    "reset_at": 1777447260,
                },
                "secondary_window": {
                    "used_percent": 41,
                    "reset_at": 1777696800,
                },
            }
        }

        provider = collect_codex(
            enabled=True,
            auth_path=Path("/tmp/auth.json"),
            usage_url="https://chatgpt.com/api/codex/usage",
            fetcher=lambda url, headers: payload,
            token_reader=lambda path: ("access-token", "account-id"),
            now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.windows["five_hour"].used_percent, 23)
        self.assertEqual(provider.windows["five_hour"].display_reset, "15:21")
        self.assertEqual(provider.windows["weekly"].used_percent, 41)
        self.assertEqual(provider.windows["weekly"].display_reset, "3d")

    def test_collect_codex_rejects_trusted_payload_missing_secondary_window(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 23,
                    "reset_at": 1777447260,
                },
            }
        }

        provider = collect_codex(
            enabled=True,
            auth_path=Path("missing-auth.json"),
            usage_url="https://chatgpt.com/api/codex/usage",
            fetcher=lambda url, headers: payload,
            token_reader=lambda path: ("access-token", "account-id"),
            now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        )

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})

    def test_collect_codex_reads_real_auth_file_for_runtime_headers(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 23,
                    "reset_at": 1777447260,
                },
                "secondary_window": {
                    "used_percent": 41,
                    "reset_at": 1777696800,
                },
            }
        }
        captured_headers: list[Mapping[str, str]] = []

        def fetcher(url: str, headers: Mapping[str, str]) -> dict[str, object]:
            captured_headers.append(headers)
            return payload

        with self.scratch_tempdir() as tmpdir:
            auth = Path(tmpdir) / "auth.json"
            auth.write_text(
                json.dumps(
                    {
                        "access_token": "auth-file-token",
                        "account_id": "auth-file-account",
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_codex(
                enabled=True,
                auth_path=auth,
                usage_url="https://chatgpt.com/api/codex/usage",
                fetcher=fetcher,
                now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(captured_headers[0]["Authorization"], "Bearer auth-file-token")
        self.assertEqual(captured_headers[0]["ChatGPT-Account-ID"], "auth-file-account")

    def test_collect_codex_falls_back_to_estimated_local_tokens(self) -> None:
        scratch_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        scratch_root.mkdir(exist_ok=True)
        env_tmpdir = os.environ.get("TMPDIR")

        def cleanup_scratch_root() -> None:
            with contextlib.suppress(OSError):
                scratch_root.rmdir()

        if not env_tmpdir or Path(env_tmpdir).resolve() != scratch_root.resolve():
            self.addCleanup(cleanup_scratch_root)

        with tempfile.TemporaryDirectory(dir=scratch_root) as tmpdir:
            sessions = Path(tmpdir) / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                json.dumps(
                    {
                        "payload": {
                            "type": "token_count",
                            "total_token_usage": {"total_tokens": 50000},
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_codex(
                enabled=True,
                auth_path=Path(tmpdir) / "missing-auth.json",
                local_fallback=True,
                codex_home=Path(tmpdir) / ".codex",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 5)
        self.assertEqual(provider.note, "local Codex token estimate")

    def test_collect_codex_falls_back_to_nested_event_msg_payload_tokens(self) -> None:
        with self.scratch_tempdir() as tmpdir:
            sessions = Path(tmpdir) / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                json.dumps(
                    {
                        "event_msg": {
                            "payload": {
                                "type": "token_count",
                                "total_token_usage": {"total_tokens": 20000},
                            }
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_codex(
                enabled=True,
                auth_path=Path(tmpdir) / "missing-auth.json",
                local_fallback=True,
                codex_home=Path(tmpdir) / ".codex",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 2)

    def test_collect_codex_sums_per_session_file_max_token_counts(self) -> None:
        with self.scratch_tempdir() as tmpdir:
            sessions = Path(tmpdir) / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "a.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"payload": {"type": "token_count", "total_tokens": 10000}}),
                        json.dumps({"payload": {"type": "token_count", "total_tokens": 30000}}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (sessions / "b.jsonl").write_text(
                json.dumps({"payload": {"type": "token_count", "total_tokens": 20000}}) + "\n",
                encoding="utf-8",
            )

            provider = collect_codex(
                enabled=True,
                auth_path=Path(tmpdir) / "missing-auth.json",
                local_fallback=True,
                codex_home=Path(tmpdir) / ".codex",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 5)

    def test_collect_codex_rejects_non_exact_usage_urls_before_reading_or_sending_token(self) -> None:
        unsafe_urls = [
            "https://chatgpt.com/api/codex/usage;x=1",
            "https://chatgpt.com/api/codex/usage?x=1",
            "https://chatgpt.com/api/codex/usage#x",
            "https://user:pass@chatgpt.com/api/codex/usage",
            "https://chatgpt.com:444/api/codex/usage",
        ]

        for usage_url in unsafe_urls:
            with self.subTest(usage_url=usage_url):
                fetcher = Mock(side_effect=AssertionError("unsafe URL should not receive a bearer token"))
                token_reader = Mock(return_value=("auth-file-token", "auth-file-account"))
                provider = collect_codex(
                    enabled=True,
                    auth_path=Path("unused-auth.json"),
                    usage_url=usage_url,
                    fetcher=fetcher,
                    token_reader=token_reader,
                )

                self.assertEqual(provider.source_status, "unknown")
                self.assertEqual(provider.windows, {})
                token_reader.assert_not_called()
                fetcher.assert_not_called()

    def test_collect_codex_rejects_unsafe_usage_url_without_injected_fetcher(self) -> None:
        with self.scratch_tempdir() as tmpdir:
            auth = Path(tmpdir) / "auth.json"
            auth.write_text(
                json.dumps(
                    {
                        "access_token": "auth-file-token",
                        "account_id": "auth-file-account",
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "paulshaclaw.cost.providers._fetch_codex_usage",
                side_effect=AssertionError("unsafe URL should not be fetched"),
            ) as fetch_mock:
                provider = collect_codex(
                    enabled=True,
                    auth_path=auth,
                    usage_url="https://example.com/api/codex/usage",
                )

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})
        fetch_mock.assert_not_called()

    def test_collect_codex_unknown_when_disabled_or_no_data(self) -> None:
        provider = collect_codex(enabled=False)

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})

    def test_collect_claude_parses_statusline_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "claude_rate_limits.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "rate_limits": {
                            "five_hour": {
                                "used_percentage": 18,
                                "resets_at": 1777447260,
                            },
                            "seven_day": {
                                "used_percentage": 41,
                                "resets_at": 1777696800,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=sidecar,
                max_age_seconds=300,
                now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.windows["five_hour"].used_percent, 18)
        self.assertEqual(provider.windows["five_hour"].display_reset, "15:21")
        self.assertEqual(provider.windows["weekly"].used_percent, 41)
        self.assertEqual(provider.windows["weekly"].display_reset, "3d")

    def test_collect_claude_parses_statusline_sidecar_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "claude_rate_limits.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "rate_limits": {
                            "five_hour": {
                                "used_percent": "100.6",
                                "reset_at": 1777447260,
                            },
                            "seven_day": {
                                "used_percent": 40.6,
                                "reset_at": 1777696800,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=sidecar,
                max_age_seconds=300,
                now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.windows["five_hour"].used_percent, 100)
        self.assertEqual(provider.windows["five_hour"].display_reset, "15:21")
        self.assertEqual(provider.windows["weekly"].used_percent, 41)
        self.assertEqual(provider.windows["weekly"].display_reset, "3d")

    def test_collect_claude_ignores_overflowing_sidecar_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "claude_rate_limits.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "rate_limits": {
                            "five_hour": {
                                "used_percentage": 18,
                                "resets_at": 10**20,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=sidecar,
                max_age_seconds=300,
                local_fallback=False,
                now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})

    def test_collect_claude_ignores_negative_sidecar_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "claude_rate_limits.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "rate_limits": {
                            "five_hour": {
                                "used_percentage": 18,
                                "resets_at": -86400,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=sidecar,
                max_age_seconds=300,
                local_fallback=False,
                now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})

    def test_collect_claude_displays_close_cross_midnight_reset_as_local_clock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "claude_rate_limits.json"
            reset_at = datetime(2026, 4, 30, 0, 15, tzinfo=ZoneInfo("Asia/Taipei"))
            sidecar.write_text(
                json.dumps(
                    {
                        "rate_limits": {
                            "five_hour": {
                                "used_percentage": 18,
                                "resets_at": reset_at.timestamp(),
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=sidecar,
                max_age_seconds=300,
                now=datetime(2026, 4, 29, 23, 30, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.windows["five_hour"].display_reset, "00:15")

    def test_collect_claude_unknown_when_sidecar_missing(self) -> None:
        provider = collect_claude(
            statusline_sidecar=Path("missing-claude-rate-limits.json"),
            local_fallback=False,
        )

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})

    def test_claude_message_token_total_excludes_local_metadata(self) -> None:
        usage = {"input_tokens": 1000, "output_tokens": 1000}

        self.assertEqual(
            _claude_message_token_total(
                {
                    "model": "claude-sonnet-4.5",
                    "provider": "local",
                    "usage": usage,
                }
            ),
            0,
        )
        self.assertEqual(
            _claude_message_token_total(
                {
                    "model": "claude-sonnet-4.5",
                    "source": "local",
                    "usage": usage,
                }
            ),
            0,
        )

    def test_collect_claude_estimated_fallback_excludes_gemma4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = Path(tmpdir) / ".claude" / "projects" / "p1"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "usage": {"input_tokens": 50, "output_tokens": 50},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "gemma4-31b-mtp",
                                    "usage": {"input_tokens": 1000, "output_tokens": 1000},
                                }
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=Path(tmpdir) / "missing.json",
                local_fallback=True,
                claude_home=Path(tmpdir) / ".claude",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 1)
        self.assertEqual(provider.note, "local Claude Code token estimate")

    def test_collect_claude_estimated_fallback_excludes_vllm_openai_compatible_and_local_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = Path(tmpdir) / ".claude" / "projects" / "p1"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "usage": {"input_tokens": 15000, "output_tokens": 5000},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "provider": "vllm",
                                    "base_url": "http://localhost:8000/v1",
                                    "usage": {"input_tokens": 900000, "output_tokens": 900000},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "source": "openai-compatible",
                                    "api_base": "http://localhost:8001/v1",
                                    "usage": {"input_tokens": 800000, "output_tokens": 800000},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "provider": "local",
                                    "usage": {"input_tokens": 700000, "output_tokens": 300000},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "source": "local",
                                    "usage": {"input_tokens": 600000, "output_tokens": 400000},
                                }
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=Path(tmpdir) / "missing.json",
                local_fallback=True,
                claude_home=Path(tmpdir) / ".claude",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 2)

    def test_collect_claude_estimated_fallback_excludes_localhost_provider_and_source_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = Path(tmpdir) / ".claude" / "projects" / "p1"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "usage": {"input_tokens": 15000, "output_tokens": 5000},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "provider": "localhost",
                                    "usage": {"input_tokens": 900000, "output_tokens": 900000},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "source": "127.0.0.1",
                                    "usage": {"input_tokens": 800000, "output_tokens": 800000},
                                }
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=Path(tmpdir) / "missing.json",
                local_fallback=True,
                claude_home=Path(tmpdir) / ".claude",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 2)


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
    def _snapshot(self, *, source_status: str = "fresh") -> CostSnapshot:
        return CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={"cdx": ProviderSnapshot(source_status=source_status, windows={})},
        )

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

    def test_main_requires_once(self) -> None:
        stderr = StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = cost_cli.main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("錯誤: Stage 8 cost CLI requires --once", stderr.getvalue())

    def test_once_cli_reports_missing_config_error(self) -> None:
        missing = Path("missing-stage8-config.yaml")

        completed = subprocess.run(
            [sys.executable, "-m", "paulshaclaw.cost", "--once", "--config", str(missing)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("錯誤: 設定檔不存在", completed.stderr)
        self.assertIn(str(missing), completed.stderr)

    def test_main_reports_value_and_os_errors(self) -> None:
        for error in (ValueError("bad config"), OSError("disk full")):
            with self.subTest(error=type(error).__name__):
                stderr = StringIO()
                with (
                    patch.object(cost_cli, "build_current_snapshot", side_effect=error),
                    contextlib.redirect_stderr(stderr),
                ):
                    exit_code = cost_cli.main(["--once"])

                self.assertEqual(exit_code, 1)
                self.assertIn(f"錯誤: {error}", stderr.getvalue())

    def test_status_main_prints_fallback_when_degraded(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with (
            patch.object(cost_status_cli, "load_cost_config", side_effect=OSError("cache unavailable")),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cost_status_cli.main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "cdx 5h:-- wk:--  cc 5h:-- wk:--")
        self.assertIn("stage8 cost status degraded: cache unavailable", stderr.getvalue())

    def test_status_main_preserves_previous_snapshot_when_refresh_fails(self) -> None:
        config = SimpleNamespace(cache_dir=Path("/ignored"), cache_ttl_seconds=120)
        previous_snapshot = self._snapshot(source_status="fresh")
        cache = Mock()
        cache.read_if_fresh.return_value = None
        cache.read_stale.return_value = previous_snapshot
        lock_cm = Mock()
        lock_cm.__enter__ = Mock(return_value=True)
        lock_cm.__exit__ = Mock(return_value=False)
        cache.lock.return_value = lock_cm
        stdout = StringIO()
        stderr = StringIO()

        def render(snapshot, *, use_tmux_style):
            self.assertEqual(snapshot.cache_status, "stale")
            self.assertEqual(snapshot.providers["cdx"].source_status, "stale")
            return "reused-stale-footer"

        with (
            patch.object(cost_status_cli, "load_cost_config", return_value=config),
            patch.object(cost_status_cli, "SnapshotCache", return_value=cache),
            patch.object(cost_status_cli, "build_current_snapshot", side_effect=RuntimeError("refresh failed")),
            patch.object(cost_status_cli, "format_footer", side_effect=render),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cost_status_cli.main(["--plain"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "reused-stale-footer")
        self.assertIn("stage8 cost status degraded: refresh failed", stderr.getvalue())

    def test_status_main_uses_fresh_cache_without_rebuild(self) -> None:
        config = SimpleNamespace(cache_dir=Path("/ignored"), cache_ttl_seconds=120)
        snapshot = self._snapshot()
        cache = Mock()
        cache.read_if_fresh.return_value = snapshot
        cache.lock.return_value = Mock()
        stdout = StringIO()

        with (
            patch.object(cost_status_cli, "load_cost_config", return_value=config),
            patch.object(cost_status_cli, "SnapshotCache", return_value=cache),
            patch.object(cost_status_cli, "format_footer", return_value="fresh-footer") as format_footer,
            patch.object(cost_status_cli, "build_current_snapshot") as build_current_snapshot,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = cost_status_cli.main(["--plain"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "fresh-footer")
        cache.read_if_fresh.assert_called_once_with()
        cache.lock.assert_not_called()
        build_current_snapshot.assert_not_called()
        format_footer.assert_called_once_with(snapshot, use_tmux_style=False)

    def test_status_main_uses_stale_cache_when_lock_unavailable(self) -> None:
        config = SimpleNamespace(cache_dir=Path("/ignored"), cache_ttl_seconds=120)
        stale_snapshot = self._snapshot(source_status="stale")
        cache = Mock()
        cache.read_if_fresh.return_value = None
        cache.read_stale.return_value = stale_snapshot
        lock_cm = Mock()
        lock_cm.__enter__ = Mock(return_value=False)
        lock_cm.__exit__ = Mock(return_value=False)
        cache.lock.return_value = lock_cm
        stdout = StringIO()

        with (
            patch.object(cost_status_cli, "load_cost_config", return_value=config),
            patch.object(cost_status_cli, "SnapshotCache", return_value=cache),
            patch.object(cost_status_cli, "format_footer", return_value="stale-footer") as format_footer,
            patch.object(cost_status_cli, "build_current_snapshot") as build_current_snapshot,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = cost_status_cli.main(["--plain"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "stale-footer")
        cache.lock.assert_called_once_with()
        lock_cm.__enter__.assert_called_once_with()
        cache.read_stale.assert_called_once_with()
        build_current_snapshot.assert_not_called()
        rendered_snapshot = format_footer.call_args.args[0]
        self.assertEqual(rendered_snapshot.cache_status, "stale")
        self.assertEqual(rendered_snapshot.providers["cdx"].source_status, "stale")
        format_footer.assert_called_once()

    def test_status_main_degrades_when_lock_unavailable_and_no_stale_cache(self) -> None:
        config = SimpleNamespace(cache_dir=Path("/ignored"), cache_ttl_seconds=120)
        cache = Mock()
        cache.read_if_fresh.return_value = None
        cache.read_stale.return_value = None
        lock_cm = Mock()
        lock_cm.__enter__ = Mock(return_value=False)
        lock_cm.__exit__ = Mock(return_value=False)
        cache.lock.return_value = lock_cm
        stdout = StringIO()

        with (
            patch.object(cost_status_cli, "load_cost_config", return_value=config),
            patch.object(cost_status_cli, "SnapshotCache", return_value=cache),
            patch.object(cost_status_cli, "build_current_snapshot") as build_current_snapshot,
            patch.object(cost_status_cli, "format_footer", return_value="degraded-footer") as format_footer,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = cost_status_cli.main(["--plain", "--config", "custom.yaml"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "degraded-footer")
        cache.lock.assert_called_once_with()
        lock_cm.__enter__.assert_called_once_with()
        cache.read_stale.assert_called_once_with()
        build_current_snapshot.assert_not_called()
        rendered_snapshot = format_footer.call_args.args[0]
        self.assertEqual(rendered_snapshot.cache_status, "stale")
        self.assertEqual(rendered_snapshot.providers["cdx"].source_status, "unknown")
        self.assertEqual(rendered_snapshot.providers["cc"].source_status, "unknown")
