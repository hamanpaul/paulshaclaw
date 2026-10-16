"""Grok 週池：只讀本機 billing log，footer 與 cockpit 都不印 5h。"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paulshaclaw.config import paths
from paulshaclaw.cost.config import (
    AgyProviderConfig,
    ClaudeProviderConfig,
    CodexProviderConfig,
    CostConfig,
    GrokProviderConfig,
    default_grok_log_path,
    parse_cost_config_payload,
)
from paulshaclaw.cost.formatter import format_cockpit_footer, format_cockpit_rest, format_footer
from paulshaclaw.cost.models import CostSnapshot, ProviderSnapshot
from paulshaclaw.cost.providers import collect_all, collect_grok
from paulshaclaw.cost.status import _build_degraded_snapshot

_NOW = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)
_END = "2026-10-23T10:00:00+00:00"


def _billing_line(
    *,
    percent: float | None,
    ts: str,
    end: str | None = _END,
    include_percent: bool = True,
) -> str:
    config: dict = {
        "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY", "end": end},
        "billingPeriodEnd": end,
    }
    if include_percent:
        config["creditUsagePercent"] = percent
    return json.dumps(
        {
            "ts": ts,
            "src": "shell",
            "msg": "billing: fetched credits config",
            "ctx": {"config": config},
        }
    )


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _config(path: Path, *, max_age: int = 3600) -> GrokProviderConfig:
    return GrokProviderConfig(enabled=True, log_path=path, max_age_seconds=max_age)


def test_collect_grok_uses_last_percent_and_ignores_file_mtime(tmp_path: Path) -> None:
    log_path = tmp_path / "unified.jsonl"
    _write_log(
        log_path,
        [
            _billing_line(percent=None, ts="2026-10-16T08:00:00+00:00", include_percent=False),
            _billing_line(percent=2.0, ts="2026-10-16T10:00:00+00:00"),
            json.dumps({"ts": "2026-10-16T10:01:00+00:00", "msg": "other"}),
        ],
    )
    os.utime(log_path, (0, 0))

    provider = collect_grok(_config(log_path), timezone_name="UTC", now=_NOW)

    assert provider.source_status == "fresh"
    assert provider.source == "local_log"
    assert provider.windows["weekly"].used_percent == 2
    assert provider.windows["weekly"].display_reset == "7d"
    assert "five_hour" not in provider.windows


def test_collect_grok_marks_old_line_stale_but_keeps_percent(tmp_path: Path) -> None:
    log_path = tmp_path / "unified.jsonl"
    old = (_NOW - timedelta(hours=2)).isoformat()
    _write_log(log_path, [_billing_line(percent=91.4, ts=old)])

    provider = collect_grok(_config(log_path), timezone_name="UTC", now=_NOW)

    assert provider.source_status == "stale"
    assert provider.windows["weekly"].used_percent == 91


def test_collect_grok_clamps_percent(tmp_path: Path) -> None:
    log_path = tmp_path / "unified.jsonl"
    _write_log(log_path, [_billing_line(percent=140, ts=_NOW.isoformat())])

    provider = collect_grok(_config(log_path), timezone_name="UTC", now=_NOW)

    assert provider.windows["weekly"].used_percent == 100


def test_collect_grok_unknown_without_log_or_reset(tmp_path: Path) -> None:
    missing = collect_grok(
        _config(tmp_path / "missing.jsonl"),
        timezone_name="UTC",
        now=_NOW,
    )
    assert missing.source_status == "unknown"
    assert missing.windows == {}

    log_path = tmp_path / "unified.jsonl"
    _write_log(
        log_path,
        [_billing_line(percent=2.0, ts=_NOW.isoformat(), end=None)],
    )
    no_reset = collect_grok(_config(log_path), timezone_name="UTC", now=_NOW)
    assert no_reset.source_status == "unknown"
    assert no_reset.windows == {}


def test_footer_and_cockpit_render_weekly_only(tmp_path: Path) -> None:
    log_path = tmp_path / "unified.jsonl"
    _write_log(log_path, [_billing_line(percent=2.0, ts=_NOW.isoformat())])
    providers = {
        "grok": collect_grok(_config(log_path), timezone_name="UTC", now=_NOW),
    }
    snapshot = CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers=providers,
    )

    footer = format_footer(snapshot, use_tmux_style=False)
    rest = _plain(format_cockpit_rest(snapshot))
    cockpit = _plain(format_cockpit_footer(snapshot))

    assert footer == "grok wk:2%(7d) "
    assert "5h" not in footer
    assert rest == "grok wk:2%(7d)"
    assert cockpit == "grok wk:2%(7d)"


def test_stale_grok_footer_uses_tilde(tmp_path: Path) -> None:
    log_path = tmp_path / "unified.jsonl"
    _write_log(
        log_path,
        [_billing_line(percent=2.0, ts=(_NOW - timedelta(hours=3)).isoformat())],
    )
    provider = collect_grok(_config(log_path), timezone_name="UTC", now=_NOW)
    snapshot = CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers={"grok": provider},
    )

    assert format_footer(snapshot, use_tmux_style=False).startswith("grok~ wk:2%")


def test_collect_all_omits_disabled_grok_and_keeps_it_when_enabled(tmp_path: Path) -> None:
    log_path = tmp_path / "unified.jsonl"
    _write_log(log_path, [_billing_line(percent=2.0, ts=_NOW.isoformat())])
    disabled = collect_all(
        CostConfig(
            codex=CodexProviderConfig(enabled=False),
            claude=ClaudeProviderConfig(enabled=False),
            agy=AgyProviderConfig(enabled=False),
            grok=GrokProviderConfig(enabled=False, log_path=log_path),
        )
    )
    assert "grok" not in disabled

    enabled = collect_all(
        CostConfig(
            codex=CodexProviderConfig(enabled=False),
            claude=ClaudeProviderConfig(enabled=False),
            agy=AgyProviderConfig(enabled=False),
            grok=GrokProviderConfig(enabled=True, log_path=log_path),
            timezone="UTC",
        )
    )
    assert enabled["grok"].windows["weekly"].used_percent == 2


def test_parse_grok_provider_defaults_enabled() -> None:
    config = parse_cost_config_payload({"cost": {"providers": {}}})
    assert config.grok.enabled is True

    disabled = parse_cost_config_payload(
        {"cost": {"providers": {"grok": {"enabled": False, "log_path": "/tmp/grok.jsonl"}}}}
    )
    assert disabled.grok.enabled is False
    assert disabled.grok.log_path == Path("/tmp/grok.jsonl")


def test_degraded_snapshot_includes_enabled_grok() -> None:
    snapshot = _build_degraded_snapshot(
        CostConfig(
            codex=CodexProviderConfig(enabled=False),
            claude=ClaudeProviderConfig(enabled=False),
            agy=AgyProviderConfig(enabled=False),
            grok=GrokProviderConfig(enabled=True),
        )
    )
    footer = format_footer(snapshot, use_tmux_style=False)
    assert footer == "grok wk:-- "
    assert "5h" not in footer


def test_default_log_path_follows_home_facade(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GROK_HOME", raising=False)
    monkeypatch.setenv("PSC_HOME_ROOT", str(tmp_path))

    assert default_grok_log_path() == paths.home_path(".grok", "logs", "unified.jsonl")
    assert default_grok_log_path() == tmp_path / ".grok" / "logs" / "unified.jsonl"


def test_grok_home_overrides_default_log_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "custom"))
    monkeypatch.setenv("PSC_HOME_ROOT", str(tmp_path / "ignored-home"))

    assert default_grok_log_path() == tmp_path / "custom" / "logs" / "unified.jsonl"


def test_unknown_provider_snapshot_still_names_grok() -> None:
    snapshot = CostSnapshot(
        generated_at=_NOW,
        timezone="UTC",
        cache_status="fresh",
        providers={"grok": ProviderSnapshot(source_status="unknown", source="unknown", windows={})},
    )
    assert format_footer(snapshot, use_tmux_style=False) == "grok wk:-- "
