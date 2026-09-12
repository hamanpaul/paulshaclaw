from __future__ import annotations

import contextlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock, patch
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
from paulshaclaw.cost.formatter import format_cockpit_rest, format_footer
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow
from paulshaclaw.cost.providers import collect_agy, collect_all
from paulshaclaw.cost.status import _build_degraded_snapshot, main as status_main

# Not a real binary — every agy test injects `runner` so the CLI branch never
# actually spawns a process; this path only has to be a truthy, non-existent
# string so `collect_agy` skips its `shutil.which("agy")` PATH lookup too.
_FAKE_AGY_CLI_PATH = "/opt/testing/fake-agy"


class _FakeCliResult:
    """Minimal stand-in for `subprocess.CompletedProcess` used by test runners."""

    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fixed_cli_runner(stdout: str, *, returncode: int = 0):
    def _runner(args, **kwargs):
        return _FakeCliResult(returncode=returncode, stdout=stdout, stderr="")

    return _runner


def _timeout_cli_runner(args, **kwargs):
    raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout", 20))


def _agy_cli_payload(
    *,
    gemini_weekly: float = 0.678,
    gemini_5h: float = 1.0,
    threep_weekly: float = 0.5,
    threep_5h: float = 0.9,
    reset_iso: str = "2026-09-12T16:54:53Z",
) -> str:
    # Shape matches the real `agy -p "/usage" --output-format json` payload
    # (agy 1.2.0, captured 2026-09-12) — see issue #353.
    return json.dumps(
        {
            "conversation_id": "c1",
            "status": "SUCCESS",
            "response": "",
            "duration_seconds": 3.1,
            "num_turns": 0,
            "usage": {},
            "command": {
                "name": "usage",
                "data": {
                    "description": "",
                    "groups": [
                        {
                            "name": "Gemini Models",
                            "description": "",
                            "buckets": [
                                {
                                    "id": "gemini-weekly",
                                    "name": "Gemini weekly",
                                    "window": "weekly",
                                    "remaining_fraction": gemini_weekly,
                                    "reset_time": reset_iso,
                                },
                                {
                                    "id": "gemini-5h",
                                    "name": "Gemini 5h",
                                    "window": "5h",
                                    "remaining_fraction": gemini_5h,
                                    "reset_time": reset_iso,
                                },
                            ],
                        },
                        {
                            "name": "Claude and GPT models",
                            "description": "",
                            "buckets": [
                                {
                                    "id": "3p-weekly",
                                    "name": "3p weekly",
                                    "window": "weekly",
                                    "remaining_fraction": threep_weekly,
                                    "reset_time": reset_iso,
                                },
                                {
                                    "id": "3p-5h",
                                    "name": "3p 5h",
                                    "window": "5h",
                                    "remaining_fraction": threep_5h,
                                    "reset_time": reset_iso,
                                },
                            ],
                        },
                    ],
                },
            },
        }
    )


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
    # #353: group/refresh_seconds/timeout_seconds/cli_path default when unset.
    assert config.agy.group == "gemini"
    assert config.agy.refresh_seconds == 300
    assert config.agy.timeout_seconds == 20
    assert config.agy.cli_path is None


def test_load_cost_config_parses_agy_cli_fields(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
        workspaces:
          - path: /repo
            name: repo
        cost:
          providers:
            agy:
              enabled: true
              group: 3p
              refresh_seconds: 120
              timeout_seconds: 5
              cli_path: /opt/testing/fake-agy
        """,
    )

    config = load_cost_config(config_path=config_path)

    assert config.agy.group == "3p"
    assert config.agy.refresh_seconds == 120
    assert config.agy.timeout_seconds == 5
    assert config.agy.cli_path == "/opt/testing/fake-agy"


def test_collect_agy_parses_percent_usage(tmp_path: Path) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    state_dir = _write_agy_state(tmp_path, {"percent_used": 42}, stamp=now)
    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            label="primary",
            state_dir=state_dir,
            local_fallback=True,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=now,
        runner=_fixed_cli_runner("", returncode=1),
        sidecar_path=tmp_path / "agy-sidecar-unused.json",
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
                cli_path=_FAKE_AGY_CLI_PATH,
            ),
            runner=_fixed_cli_runner("", returncode=1),
            sidecar_path=tmp_path / "agy-sidecar-unused.json",
        )

    assert provider is not None
    assert provider.source == "local_observed"
    assert provider.accounts[0].percent_used == 42


def test_collect_agy_parses_estimate_and_unlimited_shapes(tmp_path: Path) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    no_cli = _fixed_cli_runner("", returncode=1)
    estimate = collect_agy(
        AgyProviderConfig(
            enabled=True,
            state_dir=_write_agy_state(tmp_path / "estimate", {"remaining": 120}, stamp=now),
            local_fallback=True,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=now,
        runner=no_cli,
        sidecar_path=tmp_path / "estimate-sidecar-unused.json",
    )
    unlimited = collect_agy(
        AgyProviderConfig(
            enabled=True,
            state_dir=_write_agy_state(tmp_path / "unlimited", {"unlimited": True}, stamp=now),
            local_fallback=True,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=now,
        runner=no_cli,
        sidecar_path=tmp_path / "unlimited-sidecar-unused.json",
    )
    unknown = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=now,
        runner=no_cli,
        sidecar_path=tmp_path / "unknown-sidecar-unused.json",
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
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=now,
        runner=_fixed_cli_runner("", returncode=1),
        sidecar_path=tmp_path / "agy-sidecar-unused.json",
    )

    assert provider is not None
    assert provider.source_status == "unknown"
    assert provider.source == "unknown"
    assert provider.accounts == ()


_AGY_CLI_NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def test_collect_agy_cli_success_two_windows(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.source_status == "fresh"
    assert provider.source == "cli"
    assert set(provider.windows) == {"five_hour", "weekly"}
    # remaining_fraction=1.0 -> 0% used; remaining_fraction=0.678 -> round(32.2)=32%.
    assert provider.windows["five_hour"].used_percent == 0
    assert provider.windows["weekly"].used_percent == 32
    assert provider.windows["weekly"].reset_at is not None
    assert provider.windows["weekly"].display_reset


def test_collect_agy_cli_group_3p_reads_3p_buckets(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(enabled=True, group="3p", cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload(threep_weekly=0.2, threep_5h=0.5)),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.source == "cli"
    assert provider.windows["weekly"].used_percent == 80
    assert provider.windows["five_hour"].used_percent == 50


def test_collect_agy_cli_group_missing_falls_back_with_note(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            group="nonexistent",
            local_fallback=False,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.source_status == "unknown"
    assert provider.note == "group-missing"


def test_collect_agy_cli_timeout_falls_back_with_note(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_timeout_cli_runner,
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.source_status == "unknown"
    assert provider.note == "timeout"


def test_collect_agy_cli_nonzero_exit_falls_back_with_note(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner("", returncode=2),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.note == "nonzero"


def test_collect_agy_cli_status_not_success_falls_back_with_note(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(json.dumps({"status": "ERROR"})),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.note == "status-not-success"


def test_collect_agy_cli_invalid_json_falls_back_with_note(tmp_path: Path) -> None:
    provider = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner("not-json{"),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.note == "invalid-json"


def test_collect_agy_sidecar_throttle_skips_cli(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "agy_usage.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "fetched_at": (_AGY_CLI_NOW - timedelta(seconds=30)).isoformat(),
                "windows": {
                    "five_hour": {
                        "used_percent": 10,
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=4)).isoformat(),
                    },
                    "weekly": {
                        "used_percent": 20,
                        "reset_at": (_AGY_CLI_NOW + timedelta(days=3)).isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    runner = Mock(side_effect=AssertionError("CLI must not run within refresh_seconds"))

    provider = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=runner,
        sidecar_path=sidecar_path,
    )

    runner.assert_not_called()
    assert provider is not None
    assert provider.source_status == "fresh"
    assert provider.source == "cli"
    assert provider.windows["five_hour"].used_percent == 10
    assert provider.windows["weekly"].used_percent == 20


def test_collect_agy_cli_failure_serves_stale_sidecar(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "agy_usage.json"
    sidecar_path.write_text(
        json.dumps(
            {
                # Older than refresh_seconds=300 -> throttle window has expired.
                "fetched_at": (_AGY_CLI_NOW - timedelta(seconds=600)).isoformat(),
                "windows": {
                    "five_hour": {
                        "used_percent": 15,
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=2)).isoformat(),
                    },
                    "weekly": {
                        "used_percent": 55,
                        "reset_at": (_AGY_CLI_NOW + timedelta(days=1)).isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    provider = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner("", returncode=1),
        sidecar_path=sidecar_path,
    )

    assert provider is not None
    assert provider.source_status == "stale"
    assert provider.source == "cli"
    assert provider.windows["five_hour"].used_percent == 15
    assert provider.windows["weekly"].used_percent == 55
    assert provider.note == "nonzero"


def test_collect_agy_sidecar_file_only_has_fetched_at_and_windows(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "agy_usage.json"

    collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )

    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"fetched_at", "windows"}
    assert set(raw["windows"].keys()) == {"five_hour", "weekly"}
    for entry in raw["windows"].values():
        assert set(entry.keys()) == {"used_percent", "reset_at"}
    assert (sidecar_path.stat().st_mode & 0o777) == 0o600


@patch("paulshaclaw.cost.providers.collect_codex")
@patch("paulshaclaw.cost.providers.collect_claude")
@patch("paulshaclaw.cost.providers.collect_agy")
def test_collect_all_omits_disabled_codex_claude_copilot_and_agy(
    collect_agy_mock,
    collect_claude_mock,
    collect_codex_mock,
) -> None:
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

    collect_codex_mock.assert_not_called()
    collect_claude_mock.assert_not_called()
    collect_agy_mock.assert_not_called()
    assert providers == {}


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


def _agy_window_provider() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="fresh",
        source="cli",
        windows={
            "five_hour": UsageWindow(used_percent=0, reset_at=None, display_reset="30m"),
            "weekly": UsageWindow(used_percent=32, reset_at=None, display_reset="2d"),
        },
    )


def test_format_footer_renders_agy_windows_like_cdx_cc() -> None:
    # #353: once `windows` is populated, agy renders via `_format_window_provider`
    # (same 5h/wk shape as cdx/cc) instead of the accounts-based `agy N%` form.
    footer = format_footer(_agy_snapshot(_agy_window_provider()), use_tmux_style=False)

    assert "agy 5h:0%(30m) wk:32%(2d)" in footer


def test_format_cockpit_rest_renders_agy_windows() -> None:
    rest = format_cockpit_rest(_agy_snapshot(_agy_window_provider()))

    assert "agy" in rest
    assert "5h:" in rest
    assert "wk:" in rest


def test_build_degraded_snapshot_omits_disabled_codex_provider() -> None:
    snapshot = _build_degraded_snapshot(
        CostConfig(
            codex=CodexProviderConfig(enabled=False),
            claude=ClaudeProviderConfig(enabled=True),
        )
    )

    assert "cdx" not in snapshot.providers
    assert format_footer(snapshot, use_tmux_style=False) == "cc 5h:-- wk:-- "


def test_status_main_omits_disabled_codex_from_cached_snapshot(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    config_path = _write_config(
        tmp_path,
        f"""
        workspaces:
          - path: /repo
            name: repo
        cost:
          cache_dir: {cache_dir}
          providers:
            codex:
              enabled: false
            claude:
              enabled: true
        """,
    )
    (cache_dir / "snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-09-11T12:00:00+08:00",
                "timezone": "Asia/Taipei",
                "cache_status": "fresh",
                "providers": {
                    "cdx": {"source_status": "unknown", "source": "unknown", "windows": {}},
                    "cc": {"source_status": "unknown", "source": "unknown", "windows": {}},
                },
            }
        ),
        encoding="utf-8",
    )
    stdout = StringIO()
    stderr = StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = status_main(["--plain", "--config", str(config_path)])

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().strip() == "cc 5h:-- wk:--"
    assert "cdx" not in stdout.getvalue()


def test_sample_yaml_footer_snapshot_matches_main_baseline() -> None:
    config = load_cost_config(config_path=SAMPLE_CONFIG_PATH)
    snapshot = _build_degraded_snapshot(config)

    assert format_footer(snapshot, use_tmux_style=False) == (
        "cdx 5h:-- wk:-- | cc 5h:-- wk:-- | cpt haman:-- arc:-- "
    )
