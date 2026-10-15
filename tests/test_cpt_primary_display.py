"""Regression: secondary account state must not replace the configured primary usage."""
from datetime import datetime, timezone
import re

import pytest

from paulshaclaw.cost.formatter import format_cockpit_footer, format_footer
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot


def make_snapshot(primary_percent=87, *, secondary_status="unknown", secondary_percent=None):
    primary = CopilotAccountUsage("primary-id", "primary-label", "personal", None, 1500,
                                  "github_copilot_quota" if primary_percent is not None else "unknown",
                                  percent_used=primary_percent)
    secondary = CopilotAccountUsage("secondary-id", "secondary-label", "company", None, 300,
                                    "github_copilot_quota" if secondary_percent is not None else "unknown",
                                    percent_used=secondary_percent, source_status=secondary_status)
    return CostSnapshot(datetime.now(timezone.utc), "UTC", "fresh",
                        {"cpt": ProviderSnapshot("fresh", accounts=(primary, secondary))})


def plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.parametrize("status,percent", [("unknown", None), ("error", None),
                                          ("stale", 99), ("fresh", 99), ("estimated", 99)])
def test_secondary_state_never_replaces_primary_or_adds_account_names(status, percent):
    snap = make_snapshot(secondary_status=status, secondary_percent=percent)
    assert format_footer(snap, use_tmux_style=False) == "cpt 87% "
    assert plain(format_cockpit_footer(snap)) == "cpt: 87%"


def test_missing_primary_does_not_borrow_secondary_quota():
    snap = make_snapshot(None, secondary_status="fresh", secondary_percent=99)
    assert format_footer(snap, use_tmux_style=False) == "cpt -- "
    assert plain(format_cockpit_footer(snap)) == "cpt: --"


def test_real_banner_keeps_one_compact_cpt_line(monkeypatch):
    from paulshaclaw.cockpit import cost_bar
    from paulshaclaw.cockpit.app import CockpitApp
    monkeypatch.setattr(cost_bar, "read_snapshot", lambda: make_snapshot())
    app = CockpitApp.from_snapshot(panes=(), cockpit_pane_id="%0",
                                   cockpit_session_name="test", jobs_by_pane={}, actions=None)
    rendered = app._brand_banner_renderable()
    text = rendered.plain if hasattr(rendered, "plain") else plain(rendered)
    assert "cpt: 87%" in text
    assert len([line for line in text.splitlines() if "cpt" in line]) == 1
    for unwanted in ("primary-label", "secondary-label", "id=", "kind=", "allowance=", "source="):
        assert unwanted not in text
