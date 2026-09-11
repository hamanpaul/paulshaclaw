from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch
from zoneinfo import ZoneInfo

from paulshaclaw.cost.config import (
    AgyProviderConfig,
    ClaudeProviderConfig,
    CodexProviderConfig,
    CopilotAccountConfig,
    CostConfig,
    load_cost_config,
)
from paulshaclaw.cost.formatter import format_footer
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot
from paulshaclaw.cost.providers import collect_agy, collect_all


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "paulshaclaw.yaml"
    path.write_text(dedent(body).strip() + "\n", encoding="utf-8")
    return path


def _agy_snapshot(provider: ProviderSnapshot) -> CostSnapshot:
    return CostSnapshot(
        generated_at=datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        timezone="Asia/Taipei",
        cache_status="fresh",
        providers={"agy": provider},
    )


def test_load_cost_config_parses_agy_and_enabled_flags(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
        workspaces:
          - path: /repo
            name: repo
        cost:
          providers:
            claude:
              enabled: false
            copilot:
              accounts:
                - id: hamanpaul
                  label: haman
                  enabled: false
            agy:
              enabled: true
              source: probe
              state_path: ~/.gemini/antigravity-cli/state.json
              accounts:
                - id: main
                  label: primary
                  enabled: true
        """,
    )

    config = load_cost_config(config_path=config_path)

    assert config.claude.enabled is False
    assert config.copilot_accounts[0].enabled is False
    assert config.agy.enabled is True
    assert config.agy.source == "probe"
    assert config.agy.accounts[0].label == "primary"


@patch("paulshaclaw.cost.providers._read_json_file", return_value={"percent_used": 42})
def test_collect_agy_parses_percent_usage(read_json_file) -> None:
    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            source="probe",
            state_path=Path("unused.json"),
        )
    )

    assert provider is not None
    assert provider.source_status == "fresh"
    assert provider.accounts[0].percent_used == 42
    read_json_file.assert_called_once_with(Path("unused.json"))


def test_collect_agy_parses_estimate_and_unlimited_shapes() -> None:
    estimate = collect_agy(
        AgyProviderConfig(enabled=True, source="probe"),
        reader=lambda _path: {"remaining": 120},
    )
    unlimited = collect_agy(
        AgyProviderConfig(enabled=True, source="probe"),
        reader=lambda _path: {"unlimited": True},
    )
    unknown = collect_agy(AgyProviderConfig(enabled=True, source="unknown"))

    assert estimate is not None and estimate.source_status == "estimated"
    assert estimate.accounts[0].used_requests == 120
    assert unlimited is not None and unlimited.accounts[0].unlimited is True
    assert unknown is not None and unknown.source_status == "unknown"


@patch("paulshaclaw.cost.providers.collect_claude")
def test_collect_all_omits_disabled_claude_copilot_and_agy(collect_claude_mock) -> None:
    providers = collect_all(
        CostConfig(
            codex=CodexProviderConfig(enabled=False),
            claude=ClaudeProviderConfig(enabled=False),
            copilot_accounts=(
                CopilotAccountConfig(
                    account_id="hamanpaul",
                    label="haman",
                    kind="personal",
                    enabled=False,
                ),
            ),
            agy=AgyProviderConfig(enabled=False),
        )
    )

    collect_claude_mock.assert_not_called()
    assert set(providers) == {"cdx"}


@patch("paulshaclaw.cost.providers._read_json_file")
def test_format_footer_renders_agy_variants(_read_json_file) -> None:
    percent = ProviderSnapshot(
        source_status="fresh",
        accounts=(
            CopilotAccountUsage(
                account_id="agy",
                label="agy",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source="probe",
                percent_used=42,
            ),
        ),
    )
    estimate = ProviderSnapshot(
        source_status="estimated",
        accounts=(
            CopilotAccountUsage(
                account_id="agy",
                label="agy",
                kind="personal",
                used_requests=120,
                monthly_allowance=None,
                source="local_observed",
            ),
        ),
    )
    unknown = ProviderSnapshot(source_status="unknown", accounts=())
    unlimited = ProviderSnapshot(
        source_status="fresh",
        accounts=(
            CopilotAccountUsage(
                account_id="agy",
                label="agy",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source="probe",
                unlimited=True,
            ),
        ),
    )

    assert "agy 42%" in format_footer(_agy_snapshot(percent), use_tmux_style=False)
    assert "agy ~120" in format_footer(_agy_snapshot(estimate), use_tmux_style=False)
    assert "agy ?" in format_footer(_agy_snapshot(unknown), use_tmux_style=False)
    assert "agy ∞" in format_footer(_agy_snapshot(unlimited), use_tmux_style=False)
