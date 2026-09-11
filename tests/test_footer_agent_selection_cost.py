from __future__ import annotations

import json
import os
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
    SAMPLE_CONFIG_PATH,
    load_cost_config,
)
from paulshaclaw.cost.formatter import format_footer
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot
from paulshaclaw.cost.providers import collect_agy, collect_all
from paulshaclaw.cost.status import _build_degraded_snapshot


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


def _write_agy_state(
    tmp_path: Path,
    payload: dict[str, object],
    *,
    stamp: datetime,
) -> Path:
    state_dir = tmp_path / ".gemini" / "antigravity-cli"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    ts = stamp.timestamp()
    os.utime(state_path, (ts, ts))
    return state_dir.parent


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
              label: primary
              state_dir: ~/.gemini/antigravity-cli
              max_age_seconds: 45
              local_fallback: true
        """,
    )

    config = load_cost_config(config_path=config_path)

    assert config.claude.enabled is False
    assert config.copilot_accounts[0].enabled is False
    assert config.agy.enabled is True
    assert config.agy.label == "primary"
    assert config.agy.state_dir == Path("~/.gemini/antigravity-cli").expanduser()
    assert config.agy.max_age_seconds == 45
    assert config.agy.local_fallback is True


def test_collect_agy_parses_percent_usage(tmp_path: Path) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    state_dir = _write_agy_state(tmp_path, {"percent_used": 42}, stamp=now)
    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            label="primary",
            state_dir=state_dir,
            local_fallback=True,
        ),
        now=now,
    )

    assert provider is not None
    assert provider.source_status == "fresh"
    assert provider.source == "local_observed"
    assert provider.accounts[0].label == "primary"
    assert provider.accounts[0].percent_used == 42


def test_collect_agy_allows_default_now_when_state_is_fresh(tmp_path: Path) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    state_dir = _write_agy_state(tmp_path, {"percent_used": 42}, stamp=now)

    with patch("paulshaclaw.cost.providers._now_utc", return_value=now):
        provider = collect_agy(
            AgyProviderConfig(
                enabled=True,
                state_dir=state_dir,
                local_fallback=True,
            )
        )

    assert provider is not None
    assert provider.source == "local_observed"
    assert provider.accounts[0].percent_used == 42


def test_collect_agy_parses_estimate_and_unlimited_shapes(tmp_path: Path) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    estimate = collect_agy(
        AgyProviderConfig(
            enabled=True,
            state_dir=_write_agy_state(tmp_path / "estimate", {"remaining": 120}, stamp=now),
            local_fallback=True,
        ),
        now=now,
    )
    unlimited = collect_agy(
        AgyProviderConfig(
            enabled=True,
            state_dir=_write_agy_state(tmp_path / "unlimited", {"unlimited": True}, stamp=now),
            local_fallback=True,
        ),
        now=now,
    )
    unknown = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False),
        now=now,
    )

    assert estimate is not None and estimate.source_status == "estimated"
    assert estimate.source == "local_observed"
    assert estimate.accounts[0].used_requests == 120
    assert unlimited is not None and unlimited.source == "local_observed"
    assert unlimited.accounts[0].unlimited is True
    assert unknown is not None and unknown.source_status == "unknown"
    assert unknown.source == "unknown"


def test_collect_agy_local_fallback_requires_fresh_state(tmp_path: Path) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    state_dir = _write_agy_state(
        tmp_path,
        {"percent_used": 42},
        stamp=datetime(2026, 9, 11, 11, 40, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            state_dir=state_dir,
            max_age_seconds=300,
            local_fallback=True,
        ),
        now=now,
    )

    assert provider is not None
    assert provider.source_status == "unknown"
    assert provider.source == "unknown"
    assert provider.accounts == ()


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
        source="local_observed",
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
    api_percent = ProviderSnapshot(
        source_status="fresh",
        source="api",
        accounts=(
            CopilotAccountUsage(
                account_id="agy",
                label="agy",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source="api",
                percent_used=17,
            ),
        ),
    )
    estimate = ProviderSnapshot(
        source_status="estimated",
        source="local_observed",
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
    unknown = ProviderSnapshot(source_status="unknown", source="unknown", accounts=())
    unlimited = ProviderSnapshot(
        source_status="fresh",
        source="local_observed",
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

    assert "agy ~42" in format_footer(_agy_snapshot(percent), use_tmux_style=False)
    assert "agy 17%" in format_footer(_agy_snapshot(api_percent), use_tmux_style=False)
    assert "agy ~120" in format_footer(_agy_snapshot(estimate), use_tmux_style=False)
    assert "agy ?" in format_footer(_agy_snapshot(unknown), use_tmux_style=False)
    assert "agy ∞" in format_footer(_agy_snapshot(unlimited), use_tmux_style=False)
    assert percent.to_jsonable()["source"] == "local_observed"


def test_sample_yaml_footer_snapshot_matches_main_baseline() -> None:
    config = load_cost_config(config_path=SAMPLE_CONFIG_PATH)
    snapshot = _build_degraded_snapshot(config)

    assert format_footer(snapshot, use_tmux_style=False) == (
        "cdx 5h:-- wk:-- | cc 5h:-- wk:-- | cpt haman:-- arc:-- "
    )
