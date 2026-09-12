"""#343: agy 多帳號 `accounts[]` — config/model/provider/formatter/status 層。

新檔（而非疊加進 `tests/test_footer_agent_selection_cost.py`）避開 #353 的 EOF
衝突面；沿用該檔已驗證過的 agy CLI 測試 fixture 慣例（每個 `collect_agy()` 呼叫
一律注入 `runner=`，絕不讓真正的 agy CLI 被呼叫）。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from paulshaclaw.cost.cache import _load_provider
from paulshaclaw.cost.config import (
    AgyAccountConfig,
    AgyProviderConfig,
    ClaudeProviderConfig,
    CodexProviderConfig,
    CostConfig,
    SAMPLE_CONFIG_PATH,
    load_cost_config,
    parse_cost_config_payload,
)
from paulshaclaw.cost.formatter import _agy_name, format_cockpit_rest, format_footer
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow
from paulshaclaw.cost.providers import (
    _provider_has_data,
    carry_forward_degraded,
    collect_agy,
    collect_all,
)
from paulshaclaw.cost.status import (
    _build_degraded_snapshot,
    _filter_snapshot_by_enabled,
    _mark_snapshot_stale,
)

# 不是真正的執行檔——每個測試都注入 `runner`，所以永遠不會走到
# `shutil.which("agy")` 這條 PATH 查找路徑。
_FAKE_AGY_CLI_PATH = "/opt/testing/fake-agy-343"
_NOW = datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _guard_against_real_agy_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """比照 test_footer_agent_selection_cost.py 的同款機械化守護（#353 finding
    13）：本檔任何 `collect_agy()` 呼叫都必須帶 `runner=`，否則這裡會讓真正的
    `subprocess.run` 對 agy-like argv 直接炸掉，而不是默默打真的 CLI。
    """

    real_run = subprocess.run

    def _guarded_run(args, *a, **kw):
        argv0 = args[0] if isinstance(args, (list, tuple)) and args else args
        if isinstance(argv0, str) and "agy" in argv0:
            raise AssertionError(
                f"real subprocess.run() invoked with agy-like argv {args!r} — "
                "this collect_agy() call is missing an injected runner="
            )
        return real_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", _guarded_run)


def _agy_cli_success_payload(
    *,
    weekly: float = 0.68,
    five_hour: float = 1.0,
    reset_iso: str = "2026-09-20T00:00:00Z",
) -> str:
    return json.dumps(
        {
            "status": "SUCCESS",
            "command": {
                "data": {
                    "groups": [
                        {
                            "buckets": [
                                {
                                    "id": "gemini-weekly",
                                    "window": "weekly",
                                    "remaining_fraction": weekly,
                                    "reset_time": reset_iso,
                                },
                                {
                                    "id": "gemini-5h",
                                    "window": "5h",
                                    "remaining_fraction": five_hour,
                                    "reset_time": reset_iso,
                                },
                            ]
                        }
                    ]
                }
            },
        }
    )


def _fixed_runner(stdout: str, *, returncode: int = 0):
    def _runner(args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    return _runner


def _cost_snapshot(provider: ProviderSnapshot, *, name: str = "agy") -> CostSnapshot:
    return CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers={name: provider},
    )


def _write_agy_state(tmp_path: Path, payload: dict[str, object], *, stamp: datetime) -> Path:
    state_dir = tmp_path / ".gemini" / "antigravity-cli"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    ts = stamp.timestamp()
    os.utime(state_path, (ts, ts))
    return state_dir.parent


# --- 1. config：accounts 解析、active_account、effective_enabled ------------


def test_parse_agy_accounts_ignores_extra_keys_and_defaults_label() -> None:
    config = parse_cost_config_payload(
        {
            "cost": {
                "providers": {
                    "agy": {
                        "enabled": True,
                        "accounts": [
                            {"id": "me", "enabled": False, "kind": "company", "org": "ignored"},
                            {"id": "work", "label": "Work", "enabled": True},
                            {"id": "bare"},
                        ],
                    }
                }
            }
        }
    )

    assert config.agy.accounts == (
        AgyAccountConfig(account_id="me", label="me", enabled=False),
        AgyAccountConfig(account_id="work", label="Work", enabled=True),
        AgyAccountConfig(account_id="bare", label="bare", enabled=True),
    )
    assert config.agy.active_account == config.agy.accounts[1]
    assert config.agy.effective_enabled is True
    # 顯式序：顯式 label -> 第一個 enabled 帳號 label -> "agy"
    assert config.agy.label == "Work"


def test_agy_effective_enabled_three_states() -> None:
    no_accounts = AgyProviderConfig(enabled=True)
    assert no_accounts.effective_enabled is True
    assert no_accounts.active_account is None

    with_active = AgyProviderConfig(
        enabled=True,
        accounts=(
            AgyAccountConfig(account_id="a", label="a", enabled=False),
            AgyAccountConfig(account_id="b", label="b", enabled=True),
        ),
    )
    assert with_active.effective_enabled is True
    assert with_active.active_account is not None
    assert with_active.active_account.account_id == "b"

    all_disabled = AgyProviderConfig(
        enabled=True,
        accounts=(AgyAccountConfig(account_id="a", label="a", enabled=False),),
    )
    assert all_disabled.effective_enabled is False
    assert all_disabled.active_account is None

    top_disabled = AgyProviderConfig(
        enabled=False,
        accounts=(AgyAccountConfig(account_id="a", label="a", enabled=True),),
    )
    assert top_disabled.effective_enabled is False


def test_agy_explicit_label_wins_over_accounts() -> None:
    config = parse_cost_config_payload(
        {
            "cost": {
                "providers": {
                    "agy": {
                        "label": "explicit",
                        "accounts": [{"id": "a", "enabled": True}],
                    }
                }
            }
        }
    )
    assert config.agy.label == "explicit"


def test_sample_config_agy_accounts_is_empty_tuple() -> None:
    config = load_cost_config(config_path=SAMPLE_CONFIG_PATH)
    assert config.agy.accounts == ()


# --- 2. models/cache：label 往返、None 不輸出鍵 -------------------------------


def test_provider_snapshot_label_to_jsonable_omits_when_none() -> None:
    with_label = ProviderSnapshot(source_status="fresh", source="cli", label="work")
    without_label = ProviderSnapshot(source_status="fresh", source="cli")

    assert with_label.to_jsonable()["label"] == "work"
    assert "label" not in without_label.to_jsonable()


def test_load_provider_round_trips_label() -> None:
    with_label = ProviderSnapshot(source_status="fresh", source="cli", label="work")
    without_label = ProviderSnapshot(source_status="fresh", source="cli")

    assert _load_provider(with_label.to_jsonable()).label == "work"
    assert _load_provider(without_label.to_jsonable()).label is None


# --- 3. providers：accounts 模式、全停用、無 accounts、carry_forward、collect_all --


def test_collect_agy_cli_mode_labels_snapshot_with_active_account(tmp_path: Path) -> None:
    config = AgyProviderConfig(
        enabled=True,
        cli_path=_FAKE_AGY_CLI_PATH,
        accounts=(
            AgyAccountConfig(account_id="me", label="Me", enabled=True),
            AgyAccountConfig(account_id="work", label="Work", enabled=False),
        ),
    )
    provider = collect_agy(
        config,
        now=_NOW,
        runner=_fixed_runner(_agy_cli_success_payload()),
        sidecar_path=tmp_path / "agy_usage.json",
    )
    assert provider is not None
    assert provider.label == "Me"


def test_collect_agy_local_observed_uses_active_account_identity(tmp_path: Path) -> None:
    state_dir = _write_agy_state(tmp_path, {"percent_used": 55}, stamp=_NOW)

    def _failing_runner(args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    config = AgyProviderConfig(
        enabled=True,
        local_fallback=True,
        cli_path=_FAKE_AGY_CLI_PATH,
        state_dir=state_dir,
        accounts=(
            AgyAccountConfig(account_id="me", label="Me", enabled=True),
            AgyAccountConfig(account_id="work", label="Work", enabled=False),
        ),
    )
    provider = collect_agy(
        config,
        now=_NOW,
        runner=_failing_runner,
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.label == "Me"
    assert provider.accounts[0].account_id == "me"
    assert provider.accounts[0].label == "Me"
    assert provider.accounts[0].percent_used == 55


def test_collect_agy_all_accounts_disabled_returns_none_without_running_cli(tmp_path: Path) -> None:
    config = AgyProviderConfig(
        enabled=True,
        cli_path=_FAKE_AGY_CLI_PATH,
        accounts=(AgyAccountConfig(account_id="me", label="me", enabled=False),),
    )
    runner = Mock()
    provider = collect_agy(config, now=_NOW, runner=runner, sidecar_path=tmp_path / "agy_usage.json")

    assert provider is None
    runner.assert_not_called()


def test_collect_agy_accounts_mode_never_reads_guarded_gemini_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guarded_names = {"oauth_creds.json", "antigravity-oauth-token", "google_accounts.json"}
    original_read_text = Path.read_text

    def fail_read_text(path: Path, *args, **kwargs):
        if path.name in guarded_names:
            raise AssertionError(f"guarded read_text: {path}")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    config = AgyProviderConfig(
        enabled=True,
        cli_path=_FAKE_AGY_CLI_PATH,
        accounts=(
            AgyAccountConfig(account_id="me", label="me", enabled=True),
            AgyAccountConfig(account_id="work", label="work", enabled=False),
        ),
    )
    provider = collect_agy(
        config,
        now=_NOW,
        runner=_fixed_runner(_agy_cli_success_payload()),
        sidecar_path=tmp_path / "agy_usage.json",
    )
    assert provider is not None
    assert provider.label == "me"


def test_provider_has_data_checks_windows_even_when_accounts_present_but_empty() -> None:
    # 舊版 `if provider.accounts: ... else windows` 在 accounts 非空但無可用值
    # 時會直接回 False，完全忽略 windows —— 這是本票要改成 OR 語意要堵的洞。
    mixed = ProviderSnapshot(
        source_status="fresh",
        source="cli",
        windows={"five_hour": UsageWindow(used_percent=5, reset_at=None, display_reset="1h")},
        accounts=(
            CopilotAccountUsage(
                account_id="a",
                label="a",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source="unknown",
            ),
        ),
    )
    assert _provider_has_data(mixed) is True


def test_provider_has_data_or_semantics_basic_cases() -> None:
    only_windows = ProviderSnapshot(
        source_status="fresh",
        source="cli",
        windows={"five_hour": UsageWindow(used_percent=10, reset_at=None, display_reset="1h")},
    )
    only_accounts = ProviderSnapshot(
        source_status="fresh",
        source="local_observed",
        accounts=(
            CopilotAccountUsage(
                account_id="a",
                label="a",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source="local_state",
                percent_used=40,
            ),
        ),
    )
    neither = ProviderSnapshot(source_status="unknown", source="unknown")

    assert _provider_has_data(only_windows) is True
    assert _provider_has_data(only_accounts) is True
    assert _provider_has_data(neither) is False


def test_carry_forward_degraded_preserves_label_in_general_path() -> None:
    old = {
        "agy": ProviderSnapshot(
            source_status="fresh",
            source="cli",
            windows={"five_hour": UsageWindow(used_percent=10, reset_at=None, display_reset="1h")},
            label="work",
        )
    }
    new = {"agy": ProviderSnapshot(source_status="unknown", source="unknown", windows={}, accounts=())}

    merged = carry_forward_degraded(new, old)

    assert merged["agy"].source_status == "stale"
    assert merged["agy"].label == "work"


@patch("paulshaclaw.cost.providers.collect_agy")
def test_collect_all_skips_agy_when_all_declared_accounts_disabled(collect_agy_mock) -> None:
    providers = collect_all(
        CostConfig(
            codex=CodexProviderConfig(enabled=False),
            claude=ClaudeProviderConfig(enabled=False),
            agy=AgyProviderConfig(
                enabled=True,
                accounts=(AgyAccountConfig(account_id="a", label="a", enabled=False),),
            ),
        )
    )
    collect_agy_mock.assert_not_called()
    assert "agy" not in providers


# --- 5. formatter：agy/<label> 段名、stale 後綴、label None 維持既有字面 -----


def _labeled_account_snapshot(
    *,
    label: str | None,
    percent_used: int | None = None,
    source: str = "unknown",
    source_status: str = "unknown",
    account_source: str = "unknown",
) -> ProviderSnapshot:
    accounts: tuple[CopilotAccountUsage, ...] = ()
    if percent_used is not None:
        accounts = (
            CopilotAccountUsage(
                account_id="work",
                label="work",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source=account_source,
                percent_used=percent_used,
            ),
        )
    return ProviderSnapshot(source_status=source_status, source=source, accounts=accounts, label=label)


def _labeled_window_snapshot(*, label: str | None, source_status: str = "fresh") -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status=source_status,
        source="cli",
        windows={
            "five_hour": UsageWindow(used_percent=0, reset_at=None, display_reset="30m"),
            "weekly": UsageWindow(used_percent=32, reset_at=None, display_reset="2d"),
        },
        label=label,
    )


def test_agy_name_omits_slash_when_label_is_none() -> None:
    assert _agy_name(ProviderSnapshot(source_status="unknown", source="unknown")) == "agy"
    assert _agy_name(ProviderSnapshot(source_status="unknown", source="unknown", label="work")) == "agy/work"


def test_format_footer_agy_label_variants_no_windows() -> None:
    unknown = format_footer(_cost_snapshot(_labeled_account_snapshot(label="work")), use_tmux_style=False)
    assert "agy/work ?" in unknown

    api_percent = format_footer(
        _cost_snapshot(
            _labeled_account_snapshot(label="work", percent_used=42, source="api", account_source="api")
        ),
        use_tmux_style=False,
    )
    assert "agy/work 42%" in api_percent

    local_observed = format_footer(
        _cost_snapshot(
            _labeled_account_snapshot(
                label="work",
                percent_used=70,
                source="local_observed",
                account_source="local_observed",
            )
        ),
        use_tmux_style=False,
    )
    assert "agy/work ~70" in local_observed


def test_format_footer_agy_label_none_matches_existing_bare_literal() -> None:
    unknown = format_footer(_cost_snapshot(_labeled_account_snapshot(label=None)), use_tmux_style=False)
    assert "agy ?" in unknown
    assert "agy/" not in unknown


def test_format_footer_agy_label_prefixes_window_segment() -> None:
    footer = format_footer(_cost_snapshot(_labeled_window_snapshot(label="work")), use_tmux_style=False)
    assert "agy/work 5h:0%(30m) wk:32%(2d)" in footer


def test_format_footer_agy_label_stale_window_gets_tilde_suffix() -> None:
    footer = format_footer(
        _cost_snapshot(_labeled_window_snapshot(label="work", source_status="stale")),
        use_tmux_style=False,
    )
    assert "agy/work~ 5h:" in footer


def test_format_cockpit_rest_includes_labeled_agy_segment() -> None:
    rest = format_cockpit_rest(_cost_snapshot(_labeled_window_snapshot(label="work")))
    assert "agy/work" in rest


# --- 6. status：degraded snapshot 帶 label、全停用不 seed、filter 重標 --------


def _agy_only_config(*, accounts: tuple[AgyAccountConfig, ...]) -> CostConfig:
    return CostConfig(
        codex=CodexProviderConfig(enabled=False),
        claude=ClaudeProviderConfig(enabled=False),
        agy=AgyProviderConfig(enabled=True, accounts=accounts),
    )


def test_build_degraded_snapshot_includes_agy_label_for_active_account() -> None:
    config = _agy_only_config(
        accounts=(
            AgyAccountConfig(account_id="a", label="a", enabled=False),
            AgyAccountConfig(account_id="b", label="b", enabled=True),
        )
    )
    snapshot = _build_degraded_snapshot(config)
    assert snapshot.providers["agy"].label == "b"


def test_build_degraded_snapshot_omits_agy_when_all_accounts_disabled() -> None:
    config = _agy_only_config(accounts=(AgyAccountConfig(account_id="a", label="a", enabled=False),))
    snapshot = _build_degraded_snapshot(config)
    assert "agy" not in snapshot.providers


def test_mark_snapshot_stale_preserves_agy_label() -> None:
    snapshot = CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers={"agy": ProviderSnapshot(source_status="fresh", source="cli", windows={}, label="work")},
    )
    marked = _mark_snapshot_stale(snapshot)
    assert marked.providers["agy"].label == "work"
    assert marked.providers["agy"].source_status == "stale"


def test_filter_snapshot_by_enabled_pops_agy_when_all_accounts_disabled() -> None:
    config = _agy_only_config(accounts=(AgyAccountConfig(account_id="a", label="a", enabled=False),))
    snapshot = CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers={"agy": ProviderSnapshot(source_status="fresh", source="cli", windows={}, label="a")},
    )
    filtered = _filter_snapshot_by_enabled(snapshot, config)
    assert "agy" not in filtered.providers


def test_filter_snapshot_by_enabled_relabels_cached_agy_to_active_account() -> None:
    config = _agy_only_config(
        accounts=(
            AgyAccountConfig(account_id="a", label="a", enabled=False),
            AgyAccountConfig(account_id="b", label="b", enabled=True),
        )
    )
    snapshot = CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers={
            "agy": ProviderSnapshot(
                source_status="fresh",
                source="cli",
                windows={"five_hour": UsageWindow(used_percent=1, reset_at=None, display_reset="1h")},
                label="a",
            )
        },
    )
    filtered = _filter_snapshot_by_enabled(snapshot, config)
    assert filtered.providers["agy"].label == "b"
