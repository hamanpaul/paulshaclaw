from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

from paulshaclaw.config import paths
from paulshaclaw.cost.config import (
    AgyProviderConfig,
    ClaudeProviderConfig,
    CodexProviderConfig,
    CopilotAccountConfig,
    CostConfig,
    SAMPLE_CONFIG_PATH,
    load_cost_config,
)
from paulshaclaw.cost.formatter import (
    TMUX_COLOR_BY_LEVEL,
    format_cockpit_rest,
    format_footer,
    tmux_to_ansi_fg,
)
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow
from paulshaclaw.cost.providers import _agy_sidecar_path, _write_agy_sidecar, collect_agy, collect_all
from paulshaclaw.cost.status import _build_degraded_snapshot, main as status_main

# Not a real binary — every agy test injects `runner` so the CLI branch never
# actually spawns a process; this path only has to be a truthy, non-existent
# string so `collect_agy` skips its `shutil.which("agy")` PATH lookup too.
_FAKE_AGY_CLI_PATH = "/opt/testing/fake-agy"


@pytest.fixture(autouse=True)
def _guard_against_real_agy_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mechanized guard (#353 review finding 13): every `collect_agy()` call in
    this module must inject `runner=`. `agy` really is on this machine's PATH,
    so if a future test forgets that injection, `collect_agy`'s default
    `resolved_runner = runner or subprocess.run` would silently spawn the real
    CLI (2.5-4s / ~180MB) and write the developer's real
    `~/.agents/state/cost/agy_usage.json`. Patch the real `subprocess.run` to
    fail loudly instead whenever it's asked to run something agy-like; every
    test here supplies its own `runner=` so this never fires in a green run.
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
    # #353: group/refresh_seconds/timeout_seconds/cli_path/stale_max_age_seconds
    # default when unset.
    assert config.agy.group == "gemini"
    assert config.agy.refresh_seconds == 300
    assert config.agy.timeout_seconds == 20
    assert config.agy.cli_path is None
    assert config.agy.stale_max_age_seconds == 3600


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
              stale_max_age_seconds: 1800
        """,
    )

    config = load_cost_config(config_path=config_path)

    assert config.agy.group == "3p"
    assert config.agy.refresh_seconds == 120
    assert config.agy.timeout_seconds == 5
    assert config.agy.cli_path == "/opt/testing/fake-agy"
    assert config.agy.stale_max_age_seconds == 1800


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
    # #343: no accounts[] declared -> no multi-account label attached.
    assert provider.label is None


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


def test_collect_agy_local_fallback_note_includes_cli_failure_reason(tmp_path: Path) -> None:
    # #353 review finding 16: when the CLI source fails (here: timeout) but
    # local_fallback still has fresh local data to serve, the note must say
    # *why* the trusted CLI wasn't used instead of staying silent.
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    state_dir = _write_agy_state(tmp_path, {"percent_used": 70}, stamp=now)

    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            state_dir=state_dir,
            local_fallback=True,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=now,
        runner=_timeout_cli_runner,
        sidecar_path=tmp_path / "agy-sidecar-unused.json",
    )

    assert provider is not None
    assert provider.source == "local_observed"
    assert provider.accounts[0].percent_used == 70
    assert provider.note is not None and "timeout" in provider.note


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


def test_collect_agy_cli_invokes_expected_argv_and_timeout(tmp_path: Path) -> None:
    # #353 review finding 6: `-p "/usage"` (print mode, read-only) is what
    # makes this call zero-token / no-agent-turn; `/usage` alone or dropping
    # `-p` would start a real, quota-spending agent turn. Pin the exact argv,
    # timeout, and cwd the runner is invoked with so a future edit can't
    # silently turn this back into a real turn.
    calls: list[tuple[list[str], dict[str, object]]] = []

    def _recording_runner(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeCliResult(returncode=0, stdout=_agy_cli_payload())

    collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH, timeout_seconds=7),
        now=_AGY_CLI_NOW,
        runner=_recording_runner,
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == [_FAKE_AGY_CLI_PATH, "-p", "/usage", "--output-format", "json"]
    assert kwargs.get("timeout") == 7
    assert kwargs.get("cwd") == paths.home_root()
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True


def test_collect_agy_display_reset_uses_configured_timezone_not_utc(tmp_path: Path) -> None:
    # #353 review findings 1/14: display_reset must render in config.timezone
    # like cdx/cc do, not raw UTC — otherwise the same absolute reset instant
    # shows a different clock time for agy than for its footer neighbours.
    fixed_utc_now = datetime(2026, 9, 12, 4, 0, tzinfo=timezone.utc)  # 12:00 Asia/Taipei
    reset_iso = "2026-09-12T06:00:00Z"  # 14:00 Asia/Taipei, 2h out -> HH:MM branch

    with patch("paulshaclaw.cost.providers._now_utc", return_value=fixed_utc_now):
        provider = collect_agy(
            AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
            timezone_name="Asia/Taipei",
            runner=_fixed_cli_runner(_agy_cli_payload(reset_iso=reset_iso)),
            sidecar_path=tmp_path / "agy_usage.json",
        )

    assert provider is not None
    assert provider.windows["five_hour"].display_reset == "14:00"
    assert provider.windows["weekly"].display_reset == "14:00"


def test_collect_agy_cli_expired_reset_rolls_forward_like_codex(tmp_path: Path) -> None:
    # #353 review finding 7: a reset already in the past (CLI answered slower
    # than the window rolled over) must advance to the next window and show
    # 0% used, mirroring `_codex_window`'s roll-forward — not a stale ~100%
    # reading against an already-expired reset.
    reset_iso = "2026-09-12T11:50:00Z"  # 10 minutes before _AGY_CLI_NOW -> expired
    provider = collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload(gemini_5h=0.05, gemini_weekly=0.05, reset_iso=reset_iso)),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    five_hour = provider.windows["five_hour"]
    weekly = provider.windows["weekly"]
    assert five_hour.used_percent == 0
    assert five_hour.reset_at == datetime(2026, 9, 12, 16, 50, tzinfo=timezone.utc)
    assert weekly.used_percent == 0
    assert weekly.reset_at == datetime(2026, 9, 19, 11, 50, tzinfo=timezone.utc)


def test_collect_agy_expired_reset_stored_raw_then_failure_shows_exp_not_zero(tmp_path: Path) -> None:
    # #353 fourth-round rewrite (spec A/D/G): the sidecar always stores the
    # CLI's *raw* parsed values — roll-forward is a presentation-only step
    # (5), applied only while fresh. Cycle 1: the CLI answers with an
    # already-expired reset; the rendered snapshot rolls it forward to a
    # fresh 0%, but the on-disk `windows` block keeps the original
    # (expired) `reset_at`/`used_percent` untouched. Cycle 2: a later CLI
    # failure leaves that raw value in place and renders it as stale — back
    # to the *original* used_percent (not the fabricated 0%) with
    # `display_reset` reading "(exp)".
    sidecar_path = tmp_path / "agy_usage.json"
    reset_iso = "2026-09-12T11:50:00Z"  # 10 minutes before _AGY_CLI_NOW -> expired
    original_reset_at = datetime(2026, 9, 12, 11, 50, tzinfo=timezone.utc)

    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload(gemini_5h=0.05, gemini_weekly=0.05, reset_iso=reset_iso)),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.source_status == "fresh"
    # Rendered: rolled forward to a fresh, unused window.
    assert first.windows["five_hour"].used_percent == 0
    assert first.windows["five_hour"].reset_at != original_reset_at

    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    # Stored: the CLI's raw reading — expired reset, 95% used — untouched.
    assert raw["windows"]["five_hour"]["used_percent"] == 95
    assert raw["windows"]["five_hour"]["reset_at"] == original_reset_at.isoformat()

    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=301),
        runner=_fixed_cli_runner("", returncode=1),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.source_status == "stale"
    assert second.note == "nonzero"
    # Back to the raw, never-fabricated value — not the 0% cycle 1 rendered.
    assert second.windows["five_hour"].used_percent == 95
    assert second.windows["five_hour"].reset_at == original_reset_at
    assert second.windows["five_hour"].display_reset == "exp"


def test_collect_agy_stale_beyond_stale_max_age_drops_windows_but_keeps_note(tmp_path: Path) -> None:
    # #353 fourth-round rewrite (spec E): once `fetched_at` is older than
    # `stale_max_age_seconds`, the cached windows stop being rendered at all
    # (falling through to local_fallback/unknown) — the sidecar file itself
    # is untouched, and the last failure reason survives in `note`.
    sidecar_path = tmp_path / "agy_usage.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "attempted_at": (_AGY_CLI_NOW - timedelta(seconds=60)).isoformat(),
                "fetched_at": (_AGY_CLI_NOW - timedelta(hours=2)).isoformat(),
                "note": "nonzero",
                "windows": {
                    "five_hour": {
                        "used_percent": 33,
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=2)).isoformat(),
                    },
                    "weekly": {
                        "used_percent": 60,
                        "reset_at": (_AGY_CLI_NOW + timedelta(days=2)).isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    provider = collect_agy(
        AgyProviderConfig(
            enabled=True,
            refresh_seconds=300,
            stale_max_age_seconds=3600,
            local_fallback=False,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=_AGY_CLI_NOW,
        # attempted_at is 60s old -> throttled, no CLI call this round.
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )

    assert provider is not None
    assert provider.source_status == "unknown"
    assert provider.windows == {}
    assert provider.note == "nonzero"

    # The sidecar file itself is left exactly as it was — only the render
    # path drops the windows, not the on-disk cache.
    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert set(raw["windows"].keys()) == {"five_hour", "weekly"}


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


def test_collect_agy_cli_group_matched_but_unparseable_uses_distinct_note(tmp_path: Path) -> None:
    # #353 review finding 17 (renamed "window-unparsed" in the fourth-round
    # rewrite, spec B): a bucket whose `id` matches the configured group but
    # whose fields don't parse (unknown `window`, here) is a different
    # operator-facing cause than "no bucket matched the group at all" — the
    # former means the CLI's schema changed, the latter means `group` is
    # misconfigured. Conflating them under "group-missing" sends operators to
    # fix the wrong thing.
    payload = json.dumps(
        {
            "status": "SUCCESS",
            "command": {
                "data": {
                    "groups": [
                        {
                            "buckets": [
                                {
                                    "id": "gemini-5h",
                                    "window": "not-a-real-window",
                                    "remaining_fraction": 0.5,
                                    "reset_time": "2026-09-12T16:54:53Z",
                                },
                            ],
                        },
                    ],
                },
            },
        }
    )

    provider = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(payload),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.note == "window-unparsed"
    assert provider.note != "group-missing"


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


def test_collect_agy_sidecar_from_future_is_not_treated_as_fresh(tmp_path: Path) -> None:
    # #353 review finding 11: `fetched_at` in the future (host clock stepped
    # back, or a sidecar restored from another machine) must not throttle —
    # the `0 <= age_seconds` guard exists precisely so a clock-skewed sidecar
    # self-heals on the next call instead of being served as fresh forever.
    sidecar_path = tmp_path / "agy_usage.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "fetched_at": (_AGY_CLI_NOW + timedelta(seconds=60)).isoformat(),
                "windows": {
                    "five_hour": {
                        "used_percent": 10,
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=4)).isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    provider = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )

    assert provider is not None
    assert provider.source_status == "fresh"
    # The CLI *was* invoked (its payload's 0% for five_hour), not the stale
    # future-dated sidecar's 10%.
    assert provider.windows["five_hour"].used_percent == 0


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


def test_collect_agy_cli_failure_throttles_subsequent_calls(tmp_path: Path) -> None:
    # #353 review findings 2/15 repro (A): a non-zero exit (e.g. an expired
    # agy login) must still throttle — otherwise every ~30s cost tick reruns
    # the 2.5-4s/~180MB CLI forever. `runner`'s second element is an
    # AssertionError so a regression (CLI invoked again within
    # refresh_seconds) fails loudly instead of just returning "unknown" again.
    sidecar_path = tmp_path / "agy_usage.json"
    runner = Mock(side_effect=[_FakeCliResult(returncode=1), AssertionError("must throttle, not rerun CLI")])

    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=runner,
        sidecar_path=sidecar_path,
    )
    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=30),
        runner=runner,
        sidecar_path=sidecar_path,
    )

    assert first is not None and first.note == "nonzero"
    assert second is not None
    assert runner.call_count == 1


def test_collect_agy_cli_group_missing_throttles_subsequent_calls(tmp_path: Path) -> None:
    # #353 review findings 2/15 repro (B): CLI succeeds but the configured
    # `group` never matches a bucket (typo'd config, or the account only has
    # the other group's buckets) — this must throttle exactly like a hard CLI
    # failure, not rerun a *successful* 2.5-4s/~180MB call every ~30s forever.
    sidecar_path = tmp_path / "agy_usage.json"
    runner = Mock(
        side_effect=[
            _FakeCliResult(returncode=0, stdout=_agy_cli_payload()),
            AssertionError("must throttle, not rerun CLI"),
        ]
    )

    first = collect_agy(
        AgyProviderConfig(
            enabled=True,
            refresh_seconds=300,
            group="nonexistent",
            local_fallback=False,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=_AGY_CLI_NOW,
        runner=runner,
        sidecar_path=sidecar_path,
    )
    second = collect_agy(
        AgyProviderConfig(
            enabled=True,
            refresh_seconds=300,
            group="nonexistent",
            local_fallback=False,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=_AGY_CLI_NOW + timedelta(seconds=30),
        runner=runner,
        sidecar_path=sidecar_path,
    )

    assert first is not None and first.note == "group-missing"
    assert second is not None
    assert runner.call_count == 1


def test_collect_agy_cli_partial_parse_is_treated_as_failed_attempt(tmp_path: Path) -> None:
    # #353 fourth-round rewrite (spec B/G): a cycle that only manages to
    # parse one of the two windows is a *failed* attempt now, not a partial
    # success to merge — `windows_raw`/`fetched_at` stay exactly what they
    # were before this cycle (cycle 1's values), and `note` records
    # "window-unparsed". This replaces the third round's per-window
    # merge/eviction behaviour (review finding 5), which the final design
    # deliberately drops to cut the number of moving parts.
    sidecar_path = tmp_path / "agy_usage.json"

    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=1, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload(gemini_weekly=0.5, gemini_5h=0.9)),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.windows["five_hour"].used_percent == 10
    assert first.windows["weekly"].used_percent == 50

    # Cycle 2 (past refresh_seconds=1, so the CLI runs again): the weekly
    # bucket is missing `reset_time` this time, so only five_hour parses —
    # a failed attempt as a whole.
    partial_payload = json.dumps(
        {
            "status": "SUCCESS",
            "command": {
                "data": {
                    "groups": [
                        {
                            "buckets": [
                                {
                                    "id": "gemini-5h",
                                    "window": "5h",
                                    "remaining_fraction": 0.6,
                                    "reset_time": "2026-09-12T20:00:00Z",
                                },
                                {
                                    "id": "gemini-weekly",
                                    "window": "weekly",
                                    "remaining_fraction": 0.1,
                                },
                            ],
                        },
                    ],
                },
            },
        }
    )
    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=1, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=5),
        runner=_fixed_cli_runner(partial_payload),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.note == "window-unparsed"
    # Failed attempt: windows are byte-for-byte cycle 1's — five_hour is
    # NOT updated to this round's freshly-parsed 40%, and stays stale
    # because cycle 1's `fetched_at` is now 5s old against refresh_seconds=1.
    assert second.source_status == "stale"
    assert second.windows["five_hour"].used_percent == 10
    assert second.windows["weekly"].used_percent == 50

    # Cycle 3, throttled (within refresh_seconds of cycle 2's attempt): the
    # sidecar still carries cycle 1's untouched values and (since fetched_at
    # is only 6s old against this call's refresh_seconds=300) renders fresh.
    third = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=6),
        runner=Mock(side_effect=AssertionError("must not run again — throttled")),
        sidecar_path=sidecar_path,
    )
    assert third is not None
    assert third.source_status == "fresh"
    assert third.windows["five_hour"].used_percent == 10
    assert third.windows["weekly"].used_percent == 50


def test_collect_agy_cli_failure_after_success_stays_stale_and_keeps_note_through_throttle(
    tmp_path: Path,
) -> None:
    # #353 second-round review findings 1/2: `fetched_at` (freshness) must not
    # be conflated with `attempted_at` (throttle anchor). A CLI failure must
    # not silently promote stale cached windows back to "fresh" just because
    # the throttle anchor keeps advancing, and the failure reason (`note`)
    # must survive every throttled round instead of only the round that
    # actually ran the CLI.
    sidecar_path = tmp_path / "agy_usage.json"

    # Cycle 1: a genuine successful fetch establishes fetched_at.
    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.source_status == "fresh"

    # Cycle 2: past refresh_seconds since cycle 1's attempt -> the CLI is
    # actually invoked this round, and fails.
    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=301),
        runner=_fixed_cli_runner("", returncode=1),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.source_status == "stale"
    assert second.note == "nonzero"
    assert second.windows["five_hour"].used_percent == first.windows["five_hour"].used_percent
    assert second.windows["weekly"].used_percent == first.windows["weekly"].used_percent

    # Cycles 3 & 4: within refresh_seconds of cycle 2's *attempt* -> throttled
    # (CLI must not run again), yet still not "fresh" — fetched_at is now
    # hours-stale relative to attempted_at — and the "nonzero" note must not
    # have been dropped just because no CLI attempt ran this round.
    guard = Mock(side_effect=AssertionError("must not run CLI while throttled"))
    for offset in (30, 120):
        again = collect_agy(
            AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
            now=_AGY_CLI_NOW + timedelta(seconds=301 + offset),
            runner=guard,
            sidecar_path=sidecar_path,
        )
        assert again is not None
        assert again.source_status == "stale"
        assert again.note == "nonzero"


def test_collect_agy_cli_failure_note_persists_through_throttle_with_no_cached_windows(
    tmp_path: Path,
) -> None:
    # #353 second-round review finding 2: with no previously-cached usable
    # window at all (every attempt has failed since the sidecar was created),
    # a throttled round must still surface the CLI failure reason from the
    # sidecar rather than regressing to the generic `source="unknown"` note.
    sidecar_path = tmp_path / "agy_usage.json"

    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner("", returncode=1),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.source_status == "unknown"
    assert first.note == "nonzero"

    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=30),
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.source_status == "unknown"
    assert second.note == "nonzero"


def test_collect_agy_stale_windows_do_not_roll_forward_past_reset(tmp_path: Path) -> None:
    # #353 second-round review finding 1: a stale cached window whose
    # `reset_at` has already passed must not be silently rolled forward to a
    # fabricated `0%` — that would present fabricated data as if it were a
    # fresh, just-reset window while the CLI source is actually down.
    sidecar_path = tmp_path / "agy_usage.json"
    past_reset = _AGY_CLI_NOW - timedelta(minutes=5)
    sidecar_path.write_text(
        json.dumps(
            {
                "attempted_at": (_AGY_CLI_NOW - timedelta(seconds=600)).isoformat(),
                "fetched_at": (_AGY_CLI_NOW - timedelta(seconds=600)).isoformat(),
                "note": None,
                "windows": {
                    "five_hour": {
                        "used_percent": 80,
                        "reset_at": past_reset.isoformat(),
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
    assert provider.windows["five_hour"].used_percent == 80
    assert provider.windows["five_hour"].reset_at == past_reset


def test_collect_agy_cli_remaining_fraction_overflow_bucket_is_skipped_not_raised(tmp_path: Path) -> None:
    # #353 second-round review finding 5: an out-of-range numeric literal in
    # the CLI payload (a >1000-digit integer, which raises OverflowError from
    # `float()`) must be skipped like any other unparseable bucket instead of
    # raising out of collect_agy() — the overflowing bucket just never makes
    # it into `cli_windows`. Under the fourth-round semantics (spec B) that
    # leaves only one of the two required windows parsed, so the whole
    # attempt is a failure ("window-unparsed"), not a partial success.
    payload = {
        "status": "SUCCESS",
        "command": {
            "data": {
                "groups": [
                    {
                        "buckets": [
                            {
                                "id": "gemini-5h",
                                "window": "5h",
                                "remaining_fraction": 10**400,
                                "reset_time": "2026-09-12T20:00:00Z",
                            },
                            {
                                "id": "gemini-weekly",
                                "window": "weekly",
                                "remaining_fraction": 0.5,
                                "reset_time": "2026-09-19T20:00:00Z",
                            },
                        ],
                    },
                ],
            },
        },
    }

    provider = collect_agy(
        AgyProviderConfig(enabled=True, local_fallback=False, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(json.dumps(payload)),
        sidecar_path=tmp_path / "agy_usage.json",
    )

    assert provider is not None
    assert provider.source_status == "unknown"
    assert provider.note == "window-unparsed"
    assert provider.windows == {}


def test_collect_agy_sidecar_used_percent_overflow_entry_is_skipped_not_raised(tmp_path: Path) -> None:
    # #353 second-round review finding 5: a sidecar entry with an
    # out-of-range `used_percent` (`1e400`, parsed by JSON as float infinity,
    # which raises OverflowError from `int()`) must be skipped like any other
    # malformed cached window instead of raising.
    sidecar_path = tmp_path / "agy_usage.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "attempted_at": _AGY_CLI_NOW.isoformat(),
                "fetched_at": _AGY_CLI_NOW.isoformat(),
                "note": None,
                "windows": {
                    "five_hour": {
                        "used_percent": "__OVERFLOW__",
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=4)).isoformat(),
                    },
                    "weekly": {
                        "used_percent": 30,
                        "reset_at": (_AGY_CLI_NOW + timedelta(days=3)).isoformat(),
                    },
                },
            }
        ).replace('"__OVERFLOW__"', "1e400"),
        encoding="utf-8",
    )

    provider = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )

    assert provider is not None
    assert "five_hour" not in provider.windows
    assert provider.windows["weekly"].used_percent == 30


def test_collect_agy_sidecar_file_has_attempted_at_fetched_at_note_and_windows(tmp_path: Path) -> None:
    # #353 fourth-round rewrite (spec A/B): the sidecar's top-level shape is
    # exactly attempted_at/fetched_at/note/windows — one provider-level
    # `fetched_at` again (not per-window, spec A collapses the third round's
    # per-window schema). A successful cycle sets `fetched_at` equal to
    # `attempted_at`, clears `note`, and each window entry stores only the
    # CLI's raw parsed value (`used_percent`/`reset_at` — no per-window
    # `fetched_at` any more).
    sidecar_path = tmp_path / "agy_usage.json"

    collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )

    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"attempted_at", "fetched_at", "note", "windows"}
    assert raw["note"] is None
    assert raw["fetched_at"] == raw["attempted_at"]
    assert set(raw["windows"].keys()) == {"five_hour", "weekly"}
    for entry in raw["windows"].values():
        assert set(entry.keys()) == {"used_percent", "reset_at"}
    assert (sidecar_path.stat().st_mode & 0o777) == 0o600


def test_collect_agy_sidecar_directory_is_owner_only(tmp_path: Path) -> None:
    # #353 review finding 12: the sidecar's *directory* must be 0700, not just
    # the file — a new machine's `~/.agents/state/cost/` created at the
    # default umask would otherwise leave the directory group/world-readable.
    sidecar_path = tmp_path / "nested" / "agy_usage.json"

    collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )

    assert (sidecar_path.parent.stat().st_mode & 0o777) == 0o700


def test_write_agy_sidecar_temp_file_never_world_or_group_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #353 review finding 4: the temp file must already be owner-only (0600)
    # at creation, not rely on a post-`os.replace` chmod — otherwise there's a
    # window where the sidecar (or its default-umask temp file) is briefly
    # group/world-readable, and a failing chmod would leave it that way
    # permanently. Spy on `os.replace` to inspect the *source* file's mode
    # right before the rename: `os.replace` preserves the source inode's mode,
    # so if that's already 0600, no permissive window ever existed.
    observed_modes: list[int] = []
    real_replace = os.replace

    def _spy_replace(src, dst):
        observed_modes.append(os.stat(src).st_mode & 0o777)
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy_replace)

    sidecar_path = tmp_path / "agy_usage.json"
    _write_agy_sidecar(
        sidecar_path,
        attempted_at=_AGY_CLI_NOW,
        fetched_at=_AGY_CLI_NOW,
        note=None,
        windows_raw={"five_hour": {"used_percent": 10, "reset_at": _AGY_CLI_NOW.isoformat()}},
    )

    assert observed_modes == [0o600]
    assert (sidecar_path.stat().st_mode & 0o777) == 0o600


def test_collect_agy_sidecar_round_trip_preserves_reset_at(tmp_path: Path) -> None:
    # #353 review finding 8: cross-validate the write and read sides of the
    # sidecar — a mutation that always wrote `reset_at: null` (or renamed the
    # sidecar's path/filename) would silently drop every window on the very
    # next (throttled) read while every value-blind test stayed green.
    sidecar_path = tmp_path / "agy_usage.json"

    first = collect_agy(
        AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    expected_five_hour_reset = first.windows["five_hour"].reset_at
    expected_weekly_reset = first.windows["weekly"].reset_at
    assert expected_five_hour_reset is not None
    assert expected_weekly_reset is not None

    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=30),
        runner=Mock(side_effect=AssertionError("CLI must not run within refresh_seconds")),
        sidecar_path=sidecar_path,
    )

    assert second is not None
    assert second.source_status == "fresh"
    assert second.windows["five_hour"].reset_at == expected_five_hour_reset
    assert second.windows["weekly"].reset_at == expected_weekly_reset
    assert second.windows["five_hour"].used_percent == first.windows["five_hour"].used_percent
    assert second.windows["weekly"].used_percent == first.windows["weekly"].used_percent


def test_collect_agy_cli_partial_success_after_full_success_keeps_previous_windows_stale(
    tmp_path: Path,
) -> None:
    # #353 fourth-round rewrite (spec B/D/G, replaces the third round's
    # merge-based "no flicker" test): t0 both windows fetch fine (five_hour
    # 10%, weekly 68%). At t+3d the CLI succeeds again but the weekly bucket
    # is unparseable (no `reset_time`) — under the final design that's a
    # *failed* attempt as a whole (note "window-unparsed"), so `windows_raw`
    # stays byte-for-byte t0's values (five_hour does NOT pick up this
    # round's fresh 20%). Both rounds report the identical stale window set
    # (no flicker) with both resets now read as "(exp)" since they expired
    # long before t+3d and stale windows never roll forward. A generous
    # `stale_max_age_seconds` keeps spec E's separate age cap (its own
    # dedicated test) from kicking in here — this test is only about B/D/G.
    sidecar_path = tmp_path / "agy_usage.json"
    t0 = _AGY_CLI_NOW
    lenient_age_cap = 30 * 24 * 3600

    first = collect_agy(
        AgyProviderConfig(
            enabled=True,
            refresh_seconds=300,
            stale_max_age_seconds=lenient_age_cap,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=t0,
        runner=_fixed_cli_runner(_agy_cli_payload(gemini_weekly=0.32, gemini_5h=0.9)),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.windows["five_hour"].used_percent == 10
    assert first.windows["weekly"].used_percent == 68
    five_hour_reset_at = first.windows["five_hour"].reset_at
    weekly_reset_at = first.windows["weekly"].reset_at
    assert five_hour_reset_at is not None and weekly_reset_at is not None

    t_plus_3d = t0 + timedelta(days=3)
    assert weekly_reset_at <= t_plus_3d  # both cached resets are already past by t+3d

    partial_payload = json.dumps(
        {
            "status": "SUCCESS",
            "command": {
                "data": {
                    "groups": [
                        {
                            "buckets": [
                                {
                                    "id": "gemini-5h",
                                    "window": "5h",
                                    "remaining_fraction": 0.8,
                                    "reset_time": "2026-09-19T12:00:00Z",
                                },
                                {
                                    # Matches the group, but no `reset_time` -> unparseable.
                                    "id": "gemini-weekly",
                                    "window": "weekly",
                                    "remaining_fraction": 0.1,
                                },
                            ],
                        },
                    ],
                },
            },
        }
    )
    second = collect_agy(
        AgyProviderConfig(
            enabled=True,
            refresh_seconds=300,
            stale_max_age_seconds=lenient_age_cap,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=t_plus_3d,
        runner=_fixed_cli_runner(partial_payload),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.note == "window-unparsed"
    assert second.source_status == "stale"
    assert second.windows["five_hour"].used_percent == 10
    assert second.windows["weekly"].used_percent == 68
    assert second.windows["five_hour"].reset_at == five_hour_reset_at
    assert second.windows["weekly"].reset_at == weekly_reset_at
    assert second.windows["five_hour"].display_reset == "exp"
    assert second.windows["weekly"].display_reset == "exp"
    assert set(second.windows) == {"five_hour", "weekly"}

    third = collect_agy(
        AgyProviderConfig(
            enabled=True,
            refresh_seconds=300,
            stale_max_age_seconds=lenient_age_cap,
            cli_path=_FAKE_AGY_CLI_PATH,
        ),
        now=t_plus_3d + timedelta(seconds=30),
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )
    assert third is not None
    assert third.source_status == "stale"
    assert third.windows["five_hour"].used_percent == 10
    assert third.windows["weekly"].used_percent == 68
    assert third.windows["weekly"].display_reset == "exp"
    assert set(third.windows) == set(second.windows)


def test_collect_agy_legacy_top_level_only_sidecar_still_throttles_and_upgrades(tmp_path: Path) -> None:
    # #353 fourth-round rewrite (spec G): a first/second-round sidecar (one
    # top-level `fetched_at`, no `attempted_at`, no `windows` schema change
    # at all — its shape is a strict subset of this round's) must still
    # throttle and judge freshness exactly as a new-format sidecar would;
    # the next cycle that actually writes upgrades the file to the current
    # attempted_at/fetched_at/note/windows shape.
    sidecar_path = tmp_path / "agy_usage.json"
    legacy_fetched_at = _AGY_CLI_NOW - timedelta(seconds=30)
    sidecar_path.write_text(
        json.dumps(
            {
                "fetched_at": legacy_fetched_at.isoformat(),
                "windows": {
                    "five_hour": {
                        "used_percent": 12,
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=4)).isoformat(),
                    },
                    "weekly": {
                        "used_percent": 44,
                        "reset_at": (_AGY_CLI_NOW + timedelta(days=6)).isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    # Round A: within refresh_seconds of the legacy `fetched_at` (used as the
    # throttle anchor too, absent a real `attempted_at`) -> throttled, and
    # judged fresh exactly as a new-format sidecar would be.
    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.source_status == "fresh"
    assert first.windows["five_hour"].used_percent == 12
    assert first.windows["weekly"].used_percent == 44

    # Round B: past refresh_seconds of that same anchor -> the CLI actually
    # runs and writes the upgraded, per-window schema.
    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=301),
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.source_status == "fresh"

    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"attempted_at", "fetched_at", "note", "windows"}
    assert raw["fetched_at"] == raw["attempted_at"]
    for entry in raw["windows"].values():
        assert set(entry.keys()) == {"used_percent", "reset_at"}


def test_collect_agy_legacy_per_window_fetched_at_sidecar_still_throttles_and_upgrades(
    tmp_path: Path,
) -> None:
    # #353 fourth-round rewrite (spec G): a third-round sidecar has no
    # top-level `fetched_at` at all — freshness lived per-window back then.
    # Reading it must not raise, must pick the *oldest* of the two windows'
    # `fetched_at` values as the legacy provider-level `fetched_at` (the
    # more conservative reading — a run of throttled cycles can advance
    # `attempted_at` far past either window's actual last-fetch time), and
    # must still throttle/judge freshness correctly on this very read; the
    # next cycle that actually writes upgrades the file to the current
    # schema (no more per-window `fetched_at`).
    sidecar_path = tmp_path / "agy_usage.json"
    older_fetched_at = _AGY_CLI_NOW - timedelta(seconds=350)  # older than refresh_seconds=300
    newer_fetched_at = _AGY_CLI_NOW - timedelta(seconds=30)
    sidecar_path.write_text(
        json.dumps(
            {
                "attempted_at": newer_fetched_at.isoformat(),
                "note": None,
                "windows": {
                    "five_hour": {
                        "used_percent": 12,
                        "reset_at": (_AGY_CLI_NOW + timedelta(hours=4)).isoformat(),
                        "fetched_at": newer_fetched_at.isoformat(),
                    },
                    "weekly": {
                        "used_percent": 44,
                        "reset_at": (_AGY_CLI_NOW + timedelta(days=6)).isoformat(),
                        "fetched_at": older_fetched_at.isoformat(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    # Round A: `attempted_at` (30s old) is within refresh_seconds=300, so
    # this round throttles (no CLI call). The legacy `fetched_at` derived
    # from the windows must be the *older* of the two (350s old) — picking
    # the newer one instead would wrongly report "fresh" here.
    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW,
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.source_status == "stale"
    assert first.windows["five_hour"].used_percent == 12
    assert first.windows["weekly"].used_percent == 44

    # Round B: past refresh_seconds of `attempted_at` -> the CLI actually
    # runs and writes the upgraded, single-`fetched_at` schema.
    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, cli_path=_FAKE_AGY_CLI_PATH),
        now=_AGY_CLI_NOW + timedelta(seconds=301),
        runner=_fixed_cli_runner(_agy_cli_payload()),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.source_status == "fresh"

    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"attempted_at", "fetched_at", "note", "windows"}
    assert raw["fetched_at"] == raw["attempted_at"]
    for entry in raw["windows"].values():
        assert set(entry.keys()) == {"used_percent", "reset_at"}


def test_collect_agy_cli_missing_from_path_is_treated_as_failed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #353 third-round review finding F (required test 4): `cli_path` unset
    # in config AND not found on PATH counts as one failed attempt — it must
    # still stamp `attempted_at` (so the throttle actually engages, verified
    # here by `shutil.which` not being called a second time) and record a
    # distinguishable `note` ("cli-missing") instead of silently skipping
    # straight to local_fallback/unknown on every single cycle.
    sidecar_path = tmp_path / "agy_usage.json"
    which_calls: list[str] = []

    def _fake_which(name: str) -> str | None:
        which_calls.append(name)
        return None

    monkeypatch.setattr(shutil, "which", _fake_which)

    first = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, local_fallback=False, cli_path=None),
        now=_AGY_CLI_NOW,
        runner=Mock(side_effect=AssertionError("cli_path is None — nothing to run")),
        sidecar_path=sidecar_path,
    )
    assert first is not None
    assert first.source_status == "unknown"
    assert first.note == "cli-missing"
    assert which_calls == ["agy"]

    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert raw["note"] == "cli-missing"
    assert "attempted_at" in raw

    second = collect_agy(
        AgyProviderConfig(enabled=True, refresh_seconds=300, local_fallback=False, cli_path=None),
        now=_AGY_CLI_NOW + timedelta(seconds=30),
        runner=Mock(side_effect=AssertionError("must not run CLI while throttled")),
        sidecar_path=sidecar_path,
    )
    assert second is not None
    assert second.note == "cli-missing"
    # Still just the one `which` call from round A — throttled rounds must
    # not repeat the PATH lookup either.
    assert which_calls == ["agy"]


def test_agy_sidecar_path_matches_state_cost_agy_usage_json() -> None:
    # #353 review finding 8: pin the sidecar's default path — issue #353's
    # requirement 3 names `~/.agents/state/cost/agy_usage.json` specifically;
    # a rename here would pass every other test silently.
    assert _agy_sidecar_path() == paths.state_path("cost", "agy_usage.json")


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


@patch("paulshaclaw.cost.providers.collect_agy")
def test_collect_all_passes_config_timezone_to_agy(collect_agy_mock) -> None:
    # #353 review findings 1/14: `collect_all` must forward `config.timezone`
    # the same way it already does for collect_codex/collect_claude, instead
    # of hard-coding raw UTC for agy alone.
    collect_agy_mock.return_value = ProviderSnapshot(source_status="unknown", accounts=())
    cfg = CostConfig(
        timezone="UTC",
        codex=CodexProviderConfig(enabled=False),
        claude=ClaudeProviderConfig(enabled=False),
        agy=AgyProviderConfig(enabled=True, cli_path=_FAKE_AGY_CLI_PATH),
    )

    collect_all(cfg)

    collect_agy_mock.assert_called_once_with(cfg.agy, timezone_name="UTC")


def test_format_footer_renders_agy_variants() -> None:
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


def _tmux_segment(text: str, level: str) -> str:
    return f"#[{TMUX_COLOR_BY_LEVEL[level]}]{text}#[default]"


def test_format_cockpit_rest_renders_agy_windows() -> None:
    # #353 review finding 9: cross-validate the actual *values* (and their
    # five_hour-vs-weekly positions), not just the "5h:"/"wk:" labels — a
    # mutation that swapped the two windows' values, or the reset labels,
    # would otherwise pass silently.
    rest = format_cockpit_rest(_agy_snapshot(_agy_window_provider()))

    expected_tmux = (
        f"agy 5h:{_tmux_segment('0%', 'low')}{_tmux_segment('(30m)', 'neutral')} "
        f"wk:{_tmux_segment('32%', 'low')}{_tmux_segment('(2d)', 'neutral')}"
    )
    assert rest == tmux_to_ansi_fg(expected_tmux)


def _agy_account_provider(percent_used: int = 70) -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="fresh",
        source="local_observed",
        accounts=(
            CopilotAccountUsage(
                account_id="agy",
                label="agy",
                kind="personal",
                used_requests=None,
                monthly_allowance=None,
                source="local_state",
                percent_used=percent_used,
            ),
        ),
    )


def test_format_cockpit_rest_renders_agy_accounts_without_windows() -> None:
    # #353 review finding 9: when agy has no `windows` (CLI unavailable,
    # serving local_fallback's accounts-based estimate instead), cockpit must
    # keep rendering the accounts form (`agy ~N`) rather than degrading to the
    # windows form's `5h:-- wk:--` — a mutation that made the window branch
    # unconditional passed every other existing test here.
    rest = format_cockpit_rest(_agy_snapshot(_agy_account_provider(70)))

    assert "5h:" not in rest
    assert "wk:" not in rest
    assert rest == tmux_to_ansi_fg(f"agy {_tmux_segment('~70', 'warning')}")


def test_format_cockpit_rest_renders_agy_unknown_without_windows_or_accounts() -> None:
    # #353 second-round review finding 6: the `agy ?` branch (no windows and
    # no accounts — e.g. before collect_agy's first successful cycle) had no
    # direct assertion on format_cockpit_rest's full rendered string.
    unknown = ProviderSnapshot(source_status="unknown", source="unknown", accounts=())

    rest = format_cockpit_rest(_agy_snapshot(unknown))

    assert rest == tmux_to_ansi_fg(f"agy {_tmux_segment('?', 'neutral')}")


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
