"""Account-level collection → cache → footer/cockpit presentation contracts."""
from dataclasses import replace
from datetime import datetime, timezone
import re

import pytest

from paulshaclaw.cost.cache import SnapshotCache
from paulshaclaw.cost.config import CopilotAccountConfig, CostConfig
from paulshaclaw.cost.formatter import format_cockpit_footer, format_footer
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot
from paulshaclaw.cost.providers import carry_forward_degraded, collect_copilot


def account(label, percent=None, *, source="github_copilot_quota", **kwargs):
    return CopilotAccountUsage(label, label, "personal", None, 300, source,
                               percent_used=percent, **kwargs)


def snapshot(*accounts, status="fresh"):
    return CostSnapshot(datetime.now(timezone.utc), "UTC", "fresh",
                        {"cpt": ProviderSnapshot(status, accounts=accounts)})


def plain_ansi(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.parametrize("first,second,want", [
    (20, 69, "cpt 20% "),
    (20, 70, "cpt 20% "),
    (70, 85, "cpt 70% "),
    (85, 99, "cpt 85% "),  # equal alert class retains config order
])
def test_footer_always_uses_configured_primary(first, second, want):
    assert format_footer(snapshot(account("primary", first), account("secondary", second)),
                         use_tmux_style=False) == want


def test_unknown_secondary_does_not_hide_critical_primary():
    snap = snapshot(account("primary", 95), account("secondary", source="unknown"))
    assert format_footer(snap, use_tmux_style=False) == "cpt 95% "


def test_partial_refresh_preserves_secondary_stale_without_replacing_primary():
    old = snapshot(account("primary", 10), account("secondary", 80))
    new = snapshot(account("primary", 20), account("secondary", source="unknown"))
    providers = carry_forward_degraded(new.providers, old.providers)
    result = replace(new, providers=providers)
    assert providers["cpt"].accounts[0].percent_used == 20
    assert providers["cpt"].accounts[1].percent_used == 80
    assert providers["cpt"].accounts[1].source_status == "stale"
    assert format_footer(result, use_tmux_style=False) == "cpt 20% "
    assert "bg=colour22" not in format_footer(result)


def test_carry_forward_never_resurrects_disabled_or_removed_accounts():
    old = snapshot(account("removed", 99), account("remaining", 50))
    new = snapshot(account("remaining", source="unknown"))
    result = carry_forward_degraded(new.providers, old.providers)["cpt"]
    assert [a.account_id for a in result.accounts] == ["remaining"]
    assert result.accounts[0].percent_used == 50


def test_account_status_survives_cache_and_recovers_after_fresh_fetch(tmp_path):
    old = snapshot(account("primary", 20), account("secondary", 80))
    new = snapshot(account("primary", 21), account("secondary", source="unknown"))
    stale = replace(new, providers=carry_forward_degraded(new.providers, old.providers))
    cache = SnapshotCache(tmp_path, ttl_seconds=120)
    cache.write(stale)
    loaded = cache.read_stale()
    assert loaded.providers["cpt"].accounts[1].source_status == "stale"
    fresh = snapshot(account("primary", 22), account("secondary", 30))
    recovered = replace(fresh, providers=carry_forward_degraded(fresh.providers, loaded.providers))
    assert format_footer(recovered, use_tmux_style=False) == "cpt 22% "


def test_collector_keeps_per_account_status_and_enabled_order():
    config = CostConfig(copilot_accounts=(
        CopilotAccountConfig("disabled", "disabled", "personal", 300, enabled=False),
        CopilotAccountConfig("first", "first", "personal", 300),
        CopilotAccountConfig("second", "second", "company", 300),
    ))
    def fetcher(config_account):
        if config_account.account_id == "first":
            return 42, "github_user_billing"
        raise RuntimeError("offline")
    result = collect_copilot(config, fetcher=fetcher, local_observed={})
    assert [(a.account_id, a.source_status) for a in result.accounts] == [
        ("first", "fresh"), ("second", "unknown")]


def test_single_account_display_stays_compatible():
    snap = snapshot(account("primary", 20))
    assert format_footer(snap, use_tmux_style=False) == "cpt 20% "
    assert plain_ansi(format_cockpit_footer(snap)) == "cpt: 20%"


def test_current_config_order_and_labels_control_cached_primary():
    from paulshaclaw.cost.status import _filter_snapshot_by_enabled
    cached = snapshot(account("old", 20), account("new", 40))
    config = CostConfig(copilot_accounts=(
        CopilotAccountConfig("new", "renamed", "company", 300),
        CopilotAccountConfig("old", "old", "personal", 300),
    ))
    filtered = _filter_snapshot_by_enabled(cached, config)
    assert format_footer(filtered, use_tmux_style=False) == "cpt 40% "


def test_newly_enabled_account_is_unknown_until_first_collection():
    from paulshaclaw.cost.status import _filter_snapshot_by_enabled
    config = CostConfig(copilot_accounts=(
        CopilotAccountConfig("primary", "primary", "personal", 300),
        CopilotAccountConfig("new", "new", "company", 300),
    ))
    filtered = _filter_snapshot_by_enabled(snapshot(account("primary", 20)), config)
    assert format_footer(filtered, use_tmux_style=False) == "cpt 20% "


def test_cockpit_cache_honors_disabled_accounts(monkeypatch, tmp_path):
    from paulshaclaw.cockpit import cost_bar
    cache = SnapshotCache(tmp_path, ttl_seconds=120)
    cache.write(snapshot(account("primary", 20), account("disabled", 99)))
    config = CostConfig(cache_dir=tmp_path, copilot_accounts=(
        CopilotAccountConfig("primary", "primary", "personal", 300),
        CopilotAccountConfig("disabled", "disabled", "company", 300, enabled=False),
    ))
    monkeypatch.setattr(cost_bar, "load_cost_config", lambda: config)
    assert plain_ansi(cost_bar.cost_line(100)) == "cpt: 20%"


def test_secondary_error_and_estimate_do_not_change_primary_summary():
    error = account("secondary", source="unknown", source_status="error")
    assert format_footer(snapshot(account("primary", 95), error), use_tmux_style=False) == "cpt 95% "
    estimated = replace(account("secondary", source="local_observed", source_status="estimated"), used_requests=50)
    assert format_footer(snapshot(account("primary", 20), estimated), use_tmux_style=False) == "cpt 20% "


def test_unlimited_secondary_does_not_override_healthy_primary():
    assert format_footer(snapshot(account("primary", 20), account("secondary", unlimited=True)),
                         use_tmux_style=False) == "cpt 20% "


def test_label_control_text_cannot_inject_tmux_style_or_a_second_line():
    bad_label = "secondary#[fg=red]\n"
    line = format_footer(snapshot(account("primary", 20), account(bad_label, 95)), use_tmux_style=False)
    assert "#[" not in line
    assert "\n" not in line
    assert line == "cpt 20% "


def test_cockpit_marks_expired_cached_accounts_stale(monkeypatch, tmp_path):
    from paulshaclaw.cockpit import cost_bar
    cache = SnapshotCache(tmp_path, ttl_seconds=0)
    cache.write(snapshot(account("primary", 20), account("secondary", 30)))
    config = CostConfig(cache_dir=tmp_path, cache_ttl_seconds=0, copilot_accounts=(
        CopilotAccountConfig("primary", "primary", "personal", 300),
        CopilotAccountConfig("secondary", "secondary", "company", 300),
    ))
    monkeypatch.setattr(cost_bar, "load_cost_config", lambda: config)
    assert plain_ansi(cost_bar.cost_line(100)) == "cpt~: 20%"


def test_expired_estimated_cache_shows_stale_account_markers(monkeypatch, tmp_path):
    from paulshaclaw.cockpit import cost_bar
    estimated = replace(account("primary", source="local_observed", source_status="estimated"), used_requests=50)
    cache = SnapshotCache(tmp_path, ttl_seconds=0)
    cache.write(snapshot(estimated, replace(estimated,account_id="secondary",label="secondary"),status="estimated"))
    config = CostConfig(cache_dir=tmp_path, cache_ttl_seconds=0, copilot_accounts=(
        CopilotAccountConfig("primary", "primary", "personal", 300),
        CopilotAccountConfig("secondary", "secondary", "company", 300),
    ))
    monkeypatch.setattr(cost_bar, "load_cost_config", lambda: config)
    assert plain_ansi(cost_bar.cost_line(100)) == "cpt~: 50"


def test_enabling_copilot_without_cached_provider_exposes_unknown_accounts():
    from paulshaclaw.cost.status import _filter_snapshot_by_enabled
    config = CostConfig(copilot_accounts=(
        CopilotAccountConfig("primary", "primary", "personal", 300),
        CopilotAccountConfig("secondary", "secondary", "company", 300),
    ))
    filtered = _filter_snapshot_by_enabled(replace(snapshot(), providers={}), config)
    assert format_footer(filtered, use_tmux_style=False) == "cpt -- "
    assert len(filtered.providers["cpt"].accounts) == 2


def test_disabling_fresh_account_keeps_remaining_single_account_stale_marker():
    from paulshaclaw.cost.status import _filter_snapshot_by_enabled
    config = CostConfig(copilot_accounts=(
        CopilotAccountConfig("primary", "primary", "personal", 300, enabled=False),
        CopilotAccountConfig("secondary", "secondary", "company", 300),
    ))
    cached = snapshot(account("primary", 20), account("secondary", 80,source_status="stale"))
    filtered = _filter_snapshot_by_enabled(cached, config)
    assert format_footer(filtered, use_tmux_style=False) == "cpt~ 80% "
    assert plain_ansi(format_cockpit_footer(filtered)) == "cpt~: 80%"
