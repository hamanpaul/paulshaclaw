from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from paulshaclaw.config import paths
from paulshaclaw.cost.config import AgyProviderConfig, CopilotAccountConfig, CostConfig
from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot, UsageWindow

CopilotFetcher = Callable[[CopilotAccountConfig], tuple[int, str]]
JsonFetcher = Callable[[str, Mapping[str, str]], dict[str, Any]]
CodexTokenReader = Callable[[Path], tuple[str, str]]
_GITHUB_API_ROOT = "https://api.github.com"
_CODEX_USAGE_URL = "https://chatgpt.com/api/codex/usage"
# Copilot plan-quota endpoint — the same one the Copilot CLI statusline reads.
# Returns quota_snapshots.premium_interactions.{percent_remaining, unlimited}.
_COPILOT_USER_URL = f"{_GITHUB_API_ROOT}/copilot_internal/user"
_ACCOUNT_RE = re.compile(r"account\s+([A-Za-z0-9-]+)")
# Cap the events.jsonl fallback scan so a runaway session log can never OOM the
# host (the original unbounded 3.3GB scan crashed the WSL2 VM). Files larger
# than this are skipped; the primary plan-quota path reads no local files.
_COPILOT_EVENT_FILE_MAX_BYTES = 64 * 1024 * 1024
_CLAUDE_LOCAL_EVENT_FILE_MAX_BYTES = 64 * 1024 * 1024
_CODEX_LOCAL_EVENT_FILE_MAX_BYTES = 64 * 1024 * 1024
_LOCAL_TOKEN_WINDOW_SECONDS = 5 * 60 * 60


def _unknown_codex() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="unknown",
        source="unknown",
        windows={},
        note="trusted quota windows unavailable",
    )


def _coerce_non_negative_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError, OverflowError):
            continue
        if number < 0:
            continue
        return number
    return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _display_zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("Asia/Taipei")


def _display_reset(reset_at: datetime, now: datetime) -> str:
    local_reset = reset_at.astimezone(now.tzinfo or ZoneInfo("Asia/Taipei"))
    local_now = now.astimezone(local_reset.tzinfo)
    seconds = max(0, (local_reset - local_now).total_seconds())
    if seconds < 6 * 60 * 60:
        return local_reset.strftime("%H:%M")

    if seconds < 24 * 60 * 60:
        hours = max(1, int(seconds // 3600))
        return f"{hours}h"

    days = max(1, int((seconds + 24 * 60 * 60 - 1) // (24 * 60 * 60)))
    return f"{days}d"


def _parse_epoch(value: Any, tz: timezone | ZoneInfo) -> datetime | None:
    try:
        epoch = float(value)
        if epoch < 0:
            return None
        return datetime.fromtimestamp(epoch, timezone.utc).astimezone(tz)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _parse_reset_value(value: Any, tz: timezone | ZoneInfo) -> datetime | None:
    # A reset timestamp arrives either as an epoch number (Codex, older sidecars)
    # or as an ISO8601 string — Claude Code's statusLine payload uses ISO8601
    # (e.g. "2026-04-29T07:21:00Z"). Accept both so the statusline sidecar writer
    # can land the payload verbatim without a conversion step.
    epoch = _parse_epoch(value, tz)
    if epoch is not None:
        return epoch
    parsed = _parse_event_timestamp(value)
    if parsed is None:
        return None
    return parsed.astimezone(tz)


def _is_openai_compatible_claude_record(*records: Mapping[str, Any]) -> bool:
    excluded_markers = ("vllm", "openai-compatible", "openai_compatible")
    url_markers = ("localhost", "127.0.0.1", "0.0.0.0")

    for record in records:
        for key in ("provider", "source", "base_url", "api_base", "baseUrl", "apiBase"):
            value = record.get(key)
            if not isinstance(value, str):
                continue
            normalized = value.strip().lower()
            if any(marker in normalized for marker in excluded_markers):
                return True
            key_is_url_like = key.lower() in {"base_url", "api_base", "baseurl", "apibase"}
            key_is_provider_source = key in {"provider", "source"}
            if (key_is_url_like or key_is_provider_source) and any(marker in normalized for marker in url_markers):
                return True
            if key_is_provider_source and normalized in {"openai", "local"}:
                return True

    return False


def _window_from_rate_limit(
    rate_limit: Any,
    *,
    now: datetime,
) -> UsageWindow | None:
    if not isinstance(rate_limit, Mapping):
        return None

    raw_used_percent = rate_limit.get("used_percentage", rate_limit.get("used_percent"))
    try:
        used_percent = max(0, min(100, int(round(float(raw_used_percent)))))
    except (TypeError, ValueError, OverflowError):
        return None

    reset_at = _parse_reset_value(
        rate_limit.get("resets_at", rate_limit.get("reset_at")),
        now.tzinfo or ZoneInfo("Asia/Taipei"),
    )
    if reset_at is None:
        return None

    return UsageWindow(
        used_percent=used_percent,
        reset_at=reset_at,
        display_reset=_display_reset(reset_at, now),
    )


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _agy_account_config(config: AgyProviderConfig) -> CopilotAccountConfig:
    # #343: in accounts[] mode, attach usage to the active (first enabled)
    # declared account's identity rather than the synthetic "agy" id — the
    # `/usage` CLI answer itself carries no account identity, so this is only
    # ever the label/id the user declared, never anything read off disk.
    active = config.active_account
    if active is not None:
        return CopilotAccountConfig(
            account_id=active.account_id,
            label=active.label,
            kind="personal",
        )
    return CopilotAccountConfig(
        account_id="agy",
        label=config.label,
        kind="personal",
    )


def _file_is_fresh(path: Path, max_age_seconds: int) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return time.time() - stat.st_mtime <= max_age_seconds


def _file_is_fresh_at(path: Path, *, max_age_seconds: int, now: datetime) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return now.timestamp() - stat.st_mtime <= max_age_seconds


def _file_in_current_token_window(path: Path, *, now: datetime) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    cutoff = now.timestamp() - _LOCAL_TOKEN_WINDOW_SECONDS
    return stat.st_mtime >= cutoff


def _claude_message_token_total(
    message: Mapping[str, Any],
    record: Mapping[str, Any] | None = None,
) -> int:
    model = message.get("model")
    if not isinstance(model, str):
        return 0

    normalized_model = model.lower()
    if not normalized_model.startswith("claude-"):
        return 0
    if any(excluded in normalized_model for excluded in ("gemma4", "vllm", "openai-compatible")):
        return 0
    records = (message, record) if record is not None else (message,)
    if _is_openai_compatible_claude_record(*records):
        return 0

    usage = message.get("usage")
    if not isinstance(usage, Mapping):
        return 0

    total = 0
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        try:
            total += int(usage.get(key, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _claude_local_token_total(claude_home: Path, *, now: datetime | None = None) -> int:
    projects = claude_home / "projects"
    if not projects.exists():
        return 0

    resolved_now = now or _now_utc()
    total = 0
    for session_path in projects.rglob("*.jsonl"):
        try:
            stat = session_path.stat()
        except OSError:
            continue
        if stat.st_size > _CLAUDE_LOCAL_EVENT_FILE_MAX_BYTES:
            continue
        if not _file_in_current_token_window(session_path, now=resolved_now):
            continue
        try:
            with session_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    message = payload.get("message")
                    if isinstance(message, Mapping):
                        total += _claude_message_token_total(message, payload)
        except OSError:
            continue
    return total


def _estimated_window_from_tokens(tokens: int) -> UsageWindow:
    return UsageWindow(
        used_percent=max(1, min(100, tokens // 10000)),
        reset_at=None,
        display_reset="local",
    )


def _read_codex_token(auth_path: Path) -> tuple[str, str]:
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid Codex auth payload")
    # Codex CLI (auth_mode=chatgpt) nests the OAuth credentials under "tokens";
    # fall back to top-level keys for older/flat auth files.
    nested = payload.get("tokens")
    source = nested if isinstance(nested, dict) else payload
    access_token = source.get("access_token")
    account_id = source.get("account_id")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("missing Codex access token")
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("missing Codex account id")
    return access_token, account_id


def _fetch_codex_usage(url: str, headers: Mapping[str, str]) -> dict[str, Any]:
    return _fetch_json(url, headers)


def _is_safe_codex_usage_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "chatgpt.com"
        and parsed.path == "/api/codex/usage"
        and parsed.params == ""
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
    )


def _codex_window(raw: Any, now: datetime) -> UsageWindow | None:
    if not isinstance(raw, Mapping):
        return None

    raw_used_percent = raw.get(
        "used_percent",
        raw.get("usedPercentage", raw.get("used_percentage")),
    )
    try:
        used_percent = max(0, min(100, int(round(float(raw_used_percent)))))
    except (TypeError, ValueError, OverflowError):
        return None

    reset_at = _parse_epoch(
        raw.get("reset_at", raw.get("resetsAt", raw.get("resets_at"))),
        now.tzinfo or ZoneInfo("Asia/Taipei"),
    )
    if reset_at is None:
        return None

    # If the window already reset (no fresh reading since Codex was last used),
    # the budget has rolled over to a new, unused window. Roll the reset time
    # forward by the window length and report 0% used — so the footer shows a
    # live `0%` instead of a bare `--` or the now-obsolete used_percent.
    if reset_at <= now:
        window_minutes = raw.get("window_minutes")
        try:
            step = timedelta(minutes=int(window_minutes))
        except (TypeError, ValueError):
            step = timedelta()
        if step.total_seconds() <= 0:
            return None
        while reset_at <= now:
            reset_at += step
        used_percent = 0

    return UsageWindow(
        used_percent=used_percent,
        reset_at=reset_at,
        display_reset=_display_reset(reset_at, now),
    )


def _codex_token_count_payload(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    payload = record.get("payload")
    if isinstance(payload, Mapping):
        return payload
    event_msg = record.get("event_msg")
    if isinstance(event_msg, Mapping):
        payload = event_msg.get("payload")
        if isinstance(payload, Mapping):
            return payload
    return None


def _codex_local_token_total(codex_home: Path, *, now: datetime | None = None) -> int:
    sessions = codex_home / "sessions"
    if not sessions.exists():
        return 0

    resolved_now = now or _now_utc()
    observed = 0
    for session_path in sessions.rglob("*.jsonl"):
        try:
            stat = session_path.stat()
        except OSError:
            continue
        if stat.st_size > _CODEX_LOCAL_EVENT_FILE_MAX_BYTES:
            continue
        if not _file_in_current_token_window(session_path, now=resolved_now):
            continue
        session_observed = 0
        try:
            with session_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    payload = _codex_token_count_payload(record)
                    if payload is None:
                        continue
                    if payload.get("type") != "token_count":
                        continue
                    # Newer Codex sessions nest usage under info.total_token_usage;
                    # older ones put total_token_usage / total_tokens on the payload.
                    total_usage = payload.get("total_token_usage")
                    if not isinstance(total_usage, Mapping):
                        info = payload.get("info")
                        if isinstance(info, Mapping):
                            total_usage = info.get("total_token_usage")
                    if isinstance(total_usage, Mapping):
                        raw_total = total_usage.get("total_tokens")
                    else:
                        raw_total = payload.get("total_tokens")
                    try:
                        session_observed = max(session_observed, int(raw_total))
                    except (TypeError, ValueError):
                        continue
        except OSError:
            continue
        observed += session_observed
    return observed


def _codex_local_rate_limits(codex_home: Path, now: datetime) -> dict[str, UsageWindow] | None:
    """Read the trusted quota Codex already wrote to its latest local session.

    Each `token_count` record carries `payload.rate_limits.{primary,secondary}`
    (used_percent + resets_at), so the real 5h/weekly quota is available without
    the (often 403) network endpoint. Only windows that have not yet reset are
    returned, so stale readings are dropped rather than shown as current."""
    sessions = codex_home / "sessions"
    if not sessions.exists():
        return None
    try:
        latest = max(sessions.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, default=None)
    except (OSError, ValueError):
        return None
    if latest is None:
        return None
    try:
        if latest.stat().st_size > _CODEX_LOCAL_EVENT_FILE_MAX_BYTES:
            return None
    except OSError:
        return None

    rate_limits: Mapping[str, Any] | None = None
    try:
        with latest.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                payload = _codex_token_count_payload(record)
                if not isinstance(payload, Mapping) or payload.get("type") != "token_count":
                    continue
                candidate = payload.get("rate_limits")
                if isinstance(candidate, Mapping):
                    rate_limits = candidate  # keep the most recent in-file reading
    except OSError:
        return None

    if not isinstance(rate_limits, Mapping):
        return None

    windows: dict[str, UsageWindow] = {}
    for key, raw in (("five_hour", rate_limits.get("primary")), ("weekly", rate_limits.get("secondary"))):
        window = _codex_window(raw, now)
        if window is not None and window.reset_at is not None and window.reset_at > now:
            windows[key] = window
    return windows or None


def collect_codex(
    *,
    enabled: bool = False,
    auth_path: Path | None = None,
    usage_url: str = _CODEX_USAGE_URL,
    max_age_seconds: int = 300,
    local_fallback: bool = False,
    codex_home: Path | None = None,
    fetcher: JsonFetcher | None = None,
    token_reader: CodexTokenReader | None = None,
    now: datetime | None = None,
    timezone: str = "Asia/Taipei",
) -> ProviderSnapshot:
    if not enabled:
        return _unknown_codex()

    resolved_now = now or _now_utc().astimezone(_display_zone(timezone))
    resolved_auth_path = auth_path or (paths.codex_root() / "auth.json")
    resolved_fetcher = fetcher or _fetch_codex_usage
    resolved_token_reader = token_reader or _read_codex_token

    # Prefer the trusted quota Codex already wrote locally (correct, no network);
    # the live usage endpoint is often 403 for non-OAuth/team plans.
    local_windows = _codex_local_rate_limits(codex_home or paths.codex_root(), resolved_now)
    if local_windows:
        return ProviderSnapshot(source_status="fresh", source="api", windows=local_windows)

    try:
        if not _is_safe_codex_usage_url(usage_url):
            raise ValueError("unsafe Codex usage URL")
        access_token, account_id = resolved_token_reader(resolved_auth_path)
        if not access_token or not account_id:
            raise ValueError("missing Codex credentials")
        payload = resolved_fetcher(
            usage_url,
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "ChatGPT-Account-ID": account_id,
            },
        )
        rate_limit = payload.get("rate_limit", payload.get("rateLimit"))
        if not isinstance(rate_limit, Mapping):
            raise ValueError("missing Codex rate limit")
        five_hour = _codex_window(rate_limit.get("primary_window"), resolved_now)
        weekly = _codex_window(rate_limit.get("secondary_window"), resolved_now)
        if five_hour is None or weekly is None:
            raise ValueError("missing Codex quota windows")
        return ProviderSnapshot(
            source_status="fresh",
            source="api",
            windows={"five_hour": five_hour, "weekly": weekly},
        )
    except Exception:
        pass

    if local_fallback:
        tokens = _codex_local_token_total(
            codex_home or paths.codex_root(),
            now=resolved_now,
        )
        if tokens > 0:
            return ProviderSnapshot(
                source_status="estimated",
                source="local_observed",
                windows={"five_hour": _estimated_window_from_tokens(tokens)},
                note="local Codex token estimate",
            )

    return _unknown_codex()


def collect_claude(
    *,
    statusline_sidecar: Path | None = None,
    max_age_seconds: int = 300,
    local_fallback: bool = False,
    claude_home: Path | None = None,
    now: datetime | None = None,
    timezone: str = "Asia/Taipei",
) -> ProviderSnapshot:
    resolved_now = now or _now_utc().astimezone(_display_zone(timezone))
    sidecar = statusline_sidecar or paths.state_path("cost", "claude_rate_limits.json")
    if _file_is_fresh(sidecar, max_age_seconds):
        payload = _read_json_file(sidecar)
        rate_limits = payload.get("rate_limits") if payload else None
        if isinstance(rate_limits, Mapping):
            five_hour = _window_from_rate_limit(rate_limits.get("five_hour"), now=resolved_now)
            weekly = _window_from_rate_limit(rate_limits.get("seven_day"), now=resolved_now)
            windows: dict[str, UsageWindow] = {}
            if five_hour is not None:
                windows["five_hour"] = five_hour
            if weekly is not None:
                windows["weekly"] = weekly
            if windows:
                return ProviderSnapshot(source_status="fresh", source="api", windows=windows)

    if local_fallback:
        tokens = _claude_local_token_total(
            claude_home or paths.claude_root(),
            now=resolved_now,
        )
        if tokens > 0:
            return ProviderSnapshot(
                source_status="estimated",
                source="local_observed",
                windows={"five_hour": _estimated_window_from_tokens(tokens)},
                note="local Claude Code token estimate",
            )

    return ProviderSnapshot(
        source_status="unknown",
        source="unknown",
        windows={},
        note="credentials or trusted quota source unavailable",
    )


def _agy_state_path(state_dir: Path) -> Path:
    if state_dir.name == "antigravity-cli":
        return state_dir / "state.json"
    return state_dir / "antigravity-cli" / "state.json"


# --- agy print-mode `/usage` CLI source (#353) ------------------------------
# `agy -p "/usage" --output-format json` answers a read-only slash command: no
# agent turn, no quota spent, no credential file read. It costs 2.5-4s though,
# so a throttle sidecar (attempted_at/fetched_at/note/windows — never the raw
# CLI stdout) caches the parsed result between calls.
#
# `collect_agy` is a straight line (#353 fourth-round review collapses the
# third round's per-window `fetched_at`/merge/eviction machinery down to
# this):
#   1. read the sidecar -> throttle on `attempted_at`
#   2. (unless throttled) run the CLI: full success (both windows parsed)
#      replaces `windows_raw`/`fetched_at` wholesale; anything else is a
#      failed attempt that only updates `attempted_at`/`note`, leaving
#      `windows_raw`/`fetched_at` exactly as they were — never merged
#   3. age cap: a `fetched_at` older than `stale_max_age_seconds` renders as
#      no windows at all (the sidecar file itself is untouched)
#   4. fresh iff `fetched_at` is within `refresh_seconds` of now, else stale
#   5. presentation only: a fresh window's already-past reset rolls forward
#      (zeroed, like `_codex_window`); a stale window's past reset instead
#      reads "(exp)" rather than rolling forward or showing a dead clock time
_AGY_WINDOW_STEP = {
    "five_hour": timedelta(hours=5),
    "weekly": timedelta(days=7),
}


def _agy_sidecar_path() -> Path:
    return paths.state_path("cost", "agy_usage.json")


def _agy_window_key(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().lower()
    if normalized in {"5h", "five_hour", "5hour"}:
        return "five_hour"
    if normalized in {"weekly", "week", "7d"}:
        return "weekly"
    return None


def _agy_parse_bucket(bucket: Mapping[str, Any], now: datetime) -> tuple[str, int, datetime] | None:
    """Parse one CLI bucket into its raw `(window_key, used_percent,
    reset_at)` — no roll-forward, no `display_reset`; those are
    presentation-layer concerns applied only when rendering (step 5), never
    before a write (spec A)."""
    window_key = _agy_window_key(bucket.get("window"))
    if window_key is None:
        return None
    try:
        remaining = float(bucket.get("remaining_fraction"))
    except (TypeError, ValueError, OverflowError):
        return None
    remaining = max(0.0, min(1.0, remaining))
    used_percent = max(0, min(100, round((1 - remaining) * 100)))
    reset_at = _parse_reset_value(bucket.get("reset_time"), now.tzinfo or ZoneInfo("Asia/Taipei"))
    if reset_at is None:
        return None
    return window_key, used_percent, reset_at


def _agy_windows_from_cli_payload(
    payload: Mapping[str, Any],
    group: str,
    now: datetime,
) -> dict[str, tuple[int, datetime]] | None:
    """Flatten every group's buckets and keep the ones whose `id` starts with
    `<group>-` (e.g. group="gemini" matches "gemini-5h"/"gemini-weekly").
    Returns `None` only when no bucket matched the group at all (note:
    "group-missing"); otherwise a dict of whichever of the two recognised
    windows parsed — 0, 1 or 2 entries. `collect_agy` treats anything short
    of both keys as a failed attempt (note: "window-unparsed"); it never
    merges a partial result into the sidecar (spec B)."""
    command = payload.get("command")
    data = command.get("data") if isinstance(command, Mapping) else None
    groups = data.get("groups") if isinstance(data, Mapping) else None
    if not isinstance(groups, list):
        return None

    prefix = f"{group}-"
    windows: dict[str, tuple[int, datetime]] = {}
    matched = False
    for entry in groups:
        if not isinstance(entry, Mapping):
            continue
        buckets = entry.get("buckets")
        if not isinstance(buckets, list):
            continue
        for bucket in buckets:
            if not isinstance(bucket, Mapping):
                continue
            bucket_id = bucket.get("id")
            if not isinstance(bucket_id, str) or not bucket_id.startswith(prefix):
                continue
            matched = True
            parsed = _agy_parse_bucket(bucket, now)
            if parsed is not None:
                key, used_percent, reset_at = parsed
                windows[key] = (used_percent, reset_at)
    if not matched:
        return None
    return windows


def _agy_cli_command(cli_path: str) -> list[str]:
    return [cli_path, "-p", "/usage", "--output-format", "json"]


def _call_agy_cli(
    cli_path: str,
    *,
    timeout_seconds: int,
    runner: Callable[..., Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Run the agy print-mode usage command. Returns (payload, error_category);
    error_category is one of timeout/nonzero/invalid-json/status-not-success,
    never the raw stdout (so a caller's note never leaks CLI output)."""
    try:
        result = runner(
            _agy_cli_command(cli_path),
            capture_output=True,
            timeout=timeout_seconds,
            cwd=paths.home_root(),
            text=True,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except OSError:
        return None, "nonzero"

    if getattr(result, "returncode", None) != 0:
        return None, "nonzero"

    stdout = getattr(result, "stdout", None)
    if not isinstance(stdout, str) or not stdout.strip():
        return None, "invalid-json"
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        return None, "invalid-json"
    if not isinstance(payload, dict):
        return None, "invalid-json"
    if payload.get("status") != "SUCCESS":
        return None, "status-not-success"
    return payload, None


def _agy_windows_to_raw(windows: Mapping[str, tuple[int, datetime]]) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "used_percent": used_percent,
            "reset_at": reset_at.isoformat() if reset_at else None,
        }
        for key, (used_percent, reset_at) in windows.items()
    }


def _read_agy_sidecar(
    path: Path,
) -> tuple[datetime, datetime | None, str | None, Mapping[str, Any]] | None:
    """Returns `(attempted_at, fetched_at, note, windows_raw)`, or `None`
    when the file is missing/unparseable. `windows_raw` holds the CLI's raw
    parsed values verbatim — never rolled forward before a write (spec A).

    Reads an older sidecar without raising (spec G): a file still on the
    third round's per-window-`fetched_at` schema has no top-level
    `fetched_at` of its own — the oldest of its windows' individual
    `fetched_at` values stands in for it (the more conservative, staler
    reading). An even older (first/second round) file already used the same
    top-level key name `fetched_at` for its single provider-wide timestamp,
    so it is picked up by the same `payload.get("fetched_at")` read with no
    extra handling. A file with no recoverable timestamp at all reads as
    `fetched_at=None` (never successfully fetched)."""
    payload = _read_json_file(path)
    if payload is None:
        return None
    windows_raw = payload.get("windows")
    if not isinstance(windows_raw, Mapping):
        return None

    fetched_at = _parse_event_timestamp(payload.get("fetched_at"))
    if fetched_at is None:
        legacy_stamps = [
            stamp
            for stamp in (
                _parse_event_timestamp(entry.get("fetched_at"))
                for entry in windows_raw.values()
                if isinstance(entry, Mapping)
            )
            if stamp is not None
        ]
        if legacy_stamps:
            fetched_at = min(legacy_stamps)

    attempted_at = _parse_event_timestamp(payload.get("attempted_at")) or fetched_at
    if attempted_at is None:
        return None

    note = payload.get("note")
    if not isinstance(note, str):
        note = None

    return attempted_at, fetched_at, note, windows_raw


def _agy_render_window(
    window_key: str,
    used_percent: int,
    reset_at: datetime,
    now: datetime,
    *,
    roll_forward: bool,
) -> UsageWindow:
    """Presentation layer only (step 5): turns a sidecar's *raw* values into
    a displayable `UsageWindow`. A fresh window (`roll_forward=True`) whose
    reset has already passed is advanced to the next window and reported as
    a fresh, unused 0% — mirroring `_codex_window`'s roll-forward. A stale
    window is never rolled forward — that would fabricate a `0%` the
    operator would mistake for real data — so its `display_reset` reads
    "exp" instead of a past clock time when its reset has passed, letting
    the stale styling on the percent/reset pair carry the "not trustworthy"
    signal instead."""
    if roll_forward and reset_at <= now:
        step = _AGY_WINDOW_STEP.get(window_key, timedelta())
        if step.total_seconds() > 0:
            while reset_at <= now:
                reset_at += step
            used_percent = 0
    if not roll_forward and reset_at <= now:
        display_reset = "exp"
    else:
        display_reset = _display_reset(reset_at, now)
    return UsageWindow(
        used_percent=used_percent,
        reset_at=reset_at,
        display_reset=display_reset,
    )


def _agy_windows_from_sidecar(
    windows_raw: Mapping[str, Any], now: datetime, *, roll_forward: bool
) -> dict[str, UsageWindow]:
    windows: dict[str, UsageWindow] = {}
    for key in ("five_hour", "weekly"):
        entry = windows_raw.get(key)
        if not isinstance(entry, Mapping):
            continue
        try:
            used_percent = int(entry.get("used_percent"))
        except (TypeError, ValueError, OverflowError):
            continue
        reset_at = _parse_reset_value(entry.get("reset_at"), now.tzinfo or ZoneInfo("Asia/Taipei"))
        if reset_at is None:
            continue
        windows[key] = _agy_render_window(key, used_percent, reset_at, now, roll_forward=roll_forward)
    return windows


def _write_agy_sidecar(
    path: Path,
    *,
    attempted_at: datetime,
    fetched_at: datetime | None,
    note: str | None,
    windows_raw: Mapping[str, Any],
) -> None:
    """Owner-only, atomic write of the sidecar's exact on-disk shape —
    `attempted_at`/`fetched_at`/`note`/`windows`. Writes `fetched_at` and
    `windows_raw` byte-for-byte as given; this function never merges or
    evicts anything itself — the caller decides beforehand whether this
    round replaces them wholesale (full success, spec B(i)) or carries the
    previously-read values through untouched (any other outcome, spec
    B(ii))."""
    payload = {
        "attempted_at": attempted_at.astimezone(timezone.utc).isoformat(),
        "fetched_at": fetched_at.astimezone(timezone.utc).isoformat() if fetched_at else None,
        "note": note,
        "windows": dict(windows_raw),
    }
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        temp_path = path.parent / f"{path.name}.{os.getpid()}.tmp"
        # Create the temp file already owner-only (0600) instead of relying on
        # the umask default + a post-replace chmod: `os.replace` preserves the
        # source inode's mode, so there is no window where the sidecar is
        # briefly group/world-readable, and a failing chmod below can no
        # longer leave it permanently over-permissioned (#353 review finding 4).
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        pass


def _agy_fallback_note(note: str | None, cli_note: str | None) -> str | None:
    """Thread this cycle's CLI failure reason (if any) into a local_fallback /
    unknown note, so an operator looking at the JSON note can tell *why* the
    trusted CLI source wasn't used instead of only seeing the fallback's own
    generic text (#353 review finding 16)."""
    if cli_note is None:
        return note
    if note is None:
        return f"agy cli:{cli_note}"
    return f"{note} (agy cli:{cli_note})"


def _collect_agy_usage(
    config: AgyProviderConfig,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Taipei",
    reader: Callable[[Path], dict[str, Any] | None] | None = None,
    runner: Callable[..., Any] | None = None,
    sidecar_path: Path | None = None,
) -> ProviderSnapshot | None:
    # Mirror collect_codex/collect_claude: display_reset renders in the wall
    # clock of `timezone_name` (config.timezone), not raw UTC — otherwise
    # agy's reset time in the footer reads hours off from cdx/cc (#353 review
    # findings 1/14).
    resolved_now = now or _now_utc().astimezone(_display_zone(timezone_name))
    resolved_sidecar_path = sidecar_path or _agy_sidecar_path()
    resolved_runner = runner or subprocess.run

    # 1. Read the sidecar and throttle on `attempted_at` (last attempt, any
    #    outcome) — never on whether it produced usable windows, or every
    #    failed/unmatched cycle would re-invoke the 2.5-4s/~180MB CLI every
    #    call (#353 review findings 2/15).
    sidecar = _read_agy_sidecar(resolved_sidecar_path)
    fetched_at: datetime | None = None
    note: str | None = None
    windows_raw: Mapping[str, Any] = {}
    throttled = False
    if sidecar is not None:
        attempted_at, fetched_at, note, windows_raw = sidecar
        attempted_age_seconds = (resolved_now - attempted_at).total_seconds()
        if 0 <= attempted_age_seconds < config.refresh_seconds:
            throttled = True

    # 2. CLI attempt, skipped while throttled. Exactly two outcomes (spec B):
    #    both windows parse -> replace `windows_raw`/`fetched_at` wholesale
    #    and clear `note`; anything else is a failed attempt that leaves
    #    `windows_raw`/`fetched_at` exactly as read and only updates `note`
    #    — never a merge. A missing `cli_path` (unset in config and not on
    #    PATH) counts as one such failed attempt too, with its own note
    #    ("cli-missing") — it still stamps `attempted_at` so a repeat PATH
    #    lookup doesn't happen every call (#353 third-round review finding F).
    if not throttled:
        cli_path = config.cli_path or shutil.which("agy")
        if not cli_path:
            note = "cli-missing"
        else:
            payload, error = _call_agy_cli(
                cli_path,
                timeout_seconds=config.timeout_seconds,
                runner=resolved_runner,
            )
            if error is not None:
                note = error
            else:
                cli_windows = _agy_windows_from_cli_payload(payload, config.group, resolved_now)
                if cli_windows is None:
                    note = "group-missing"
                elif set(cli_windows) != set(_AGY_WINDOW_STEP):
                    # Matched the group but didn't parse *both* recognised
                    # windows — a partial result is a failed attempt, not a
                    # partial success (spec B): the previously-read
                    # `windows_raw`/`fetched_at` are kept exactly as they
                    # were rather than merged with this round's subset.
                    note = "window-unparsed"
                else:
                    note = None
                    windows_raw = _agy_windows_to_raw(cli_windows)
                    fetched_at = resolved_now
        _write_agy_sidecar(
            resolved_sidecar_path,
            attempted_at=resolved_now,
            fetched_at=fetched_at,
            note=note,
            windows_raw=windows_raw,
        )

    # 3. Age cap (spec E): a `fetched_at` older than `stale_max_age_seconds`
    #    (or a clock-skewed future one) renders as no windows at all — the
    #    sidecar file itself is untouched, but continuing to show hours-old
    #    numbers as this provider's only signal would be more misleading
    #    than falling through to local_fallback/unknown below, which still
    #    carries `note` forward.
    if fetched_at is not None and windows_raw:
        age_seconds = (resolved_now - fetched_at).total_seconds()
        if not (0 <= age_seconds < config.stale_max_age_seconds):
            windows_raw = {}

    # 4. Render straight from the sidecar's windows (spec D) — the same code
    #    path for a CLI-run cycle and a throttled one alike, so there is no
    #    flicker between "this round's subset" and "the cached windows".
    #    Fresh iff `fetched_at` itself is within `refresh_seconds` of now; a
    #    fresh window's expired reset rolls forward, a stale one instead
    #    reads "(exp)" (step 5, in `_agy_render_window`).
    if windows_raw:
        fresh = fetched_at is not None and 0 <= (resolved_now - fetched_at).total_seconds() < config.refresh_seconds
        rendered = _agy_windows_from_sidecar(windows_raw, resolved_now, roll_forward=fresh)
        if rendered:
            return ProviderSnapshot(
                source_status="fresh" if fresh else "stale",
                source="cli",
                windows=rendered,
                note=None if fresh else note,
            )

    # 5. Existing local_fallback / unknown flow (source priority #2/#3).
    if not config.local_fallback:
        return ProviderSnapshot(
            source_status="unknown",
            source="unknown",
            accounts=(),
            note=note or 'source="unknown"',
        )

    state_path = _agy_state_path(config.state_dir)
    if not _file_is_fresh_at(
        state_path,
        max_age_seconds=config.max_age_seconds,
        now=resolved_now,
    ):
        return ProviderSnapshot(
            source_status="unknown",
            source="unknown",
            accounts=(),
            note=_agy_fallback_note("agy quota unavailable", note),
        )

    payload = (reader or _read_json_file)(state_path)
    if not isinstance(payload, Mapping):
        return ProviderSnapshot(
            source_status="unknown",
            source="unknown",
            accounts=(),
            note=_agy_fallback_note("agy quota unavailable", note),
        )

    account = _agy_account_config(config)
    base_usage = {
        "account_id": account.account_id,
        "label": account.label,
        "kind": account.kind,
        "monthly_allowance": account.monthly_allowance,
    }

    if bool(payload.get("unlimited")):
        return ProviderSnapshot(
            source_status="fresh",
            source="local_observed",
            accounts=(
                CopilotAccountUsage(
                    used_requests=None,
                    source="local_state",
                    percent_used=None,
                    unlimited=True,
                    **base_usage,
                ),
            ),
            note=_agy_fallback_note("agy unlimited quota", note),
        )

    percent_used = _coerce_non_negative_int(
        payload.get("percent_used"),
        payload.get("used_percent"),
        payload.get("used_percentage"),
    )
    if percent_used is not None:
        return ProviderSnapshot(
            source_status="fresh",
            source="local_observed",
            accounts=(
                CopilotAccountUsage(
                    used_requests=None,
                    source="local_state",
                    percent_used=min(100, percent_used),
                    unlimited=False,
                    **base_usage,
                ),
            ),
            note=_agy_fallback_note(None, note),
        )

    approx_remaining = _coerce_non_negative_int(
        payload.get("approx_remaining"),
        payload.get("remaining"),
        payload.get("remaining_allowance"),
        payload.get("quota_remaining"),
    )
    if approx_remaining is not None:
        return ProviderSnapshot(
            source_status="estimated",
            source="local_observed",
            accounts=(
                CopilotAccountUsage(
                    used_requests=approx_remaining,
                    source="local_observed",
                    percent_used=None,
                    unlimited=False,
                    **base_usage,
                ),
            ),
            note=_agy_fallback_note("agy local estimate", note),
        )

    return ProviderSnapshot(
        source_status="unknown",
        source="unknown",
        accounts=(),
        note=_agy_fallback_note("agy quota unavailable", note),
    )


def collect_agy(
    config: AgyProviderConfig,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Taipei",
    reader: Callable[[Path], dict[str, Any] | None] | None = None,
    runner: Callable[..., Any] | None = None,
    sidecar_path: Path | None = None,
) -> ProviderSnapshot | None:
    """#343 entry point: gate on `effective_enabled` (top-level `enabled` AND,
    when accounts[] is declared, at least one of them enabled), delegate to
    `_collect_agy_usage` for the actual CLI/local-fallback/unknown flow, then
    stamp the result with the active account's label (or `None` when no
    accounts are declared, leaving the footer's bare `agy` name unchanged)."""
    if not config.effective_enabled:
        return None
    snapshot = _collect_agy_usage(
        config,
        now=now,
        timezone_name=timezone_name,
        reader=reader,
        runner=runner,
        sidecar_path=sidecar_path,
    )
    if snapshot is None:
        return None
    active = config.active_account
    return dataclasses.replace(snapshot, label=active.label if active is not None else None)


def _unknown_account(account: CopilotAccountConfig) -> CopilotAccountUsage:
    return CopilotAccountUsage(
        account_id=account.account_id,
        label=account.label,
        kind=account.kind,
        used_requests=None,
        monthly_allowance=account.monthly_allowance,
        source="unknown",
    )


def _get_github_token(account_id: str) -> str:
    completed = subprocess.run(
        ["gh", "auth", "token", "-u", account_id],
        check=True,
        capture_output=True,
        text=True,
    )
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("missing GitHub token")
    return token


def _fetch_json(url: str, headers: Mapping[str, str]) -> dict[str, Any]:
    request = Request(
        url,
        headers=dict(headers),
        method="GET",
    )
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("unexpected GitHub API payload")
    return payload


def _current_month_utc() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return now.year, now.month


def _usage_item_quantity(item: Mapping[str, Any]) -> int | None:
    for key in ("grossQuantity", "netQuantity", "quantity", "total"):
        value = item.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _extract_usage_items_total(payload: Mapping[str, Any]) -> int:
    items = payload.get("usageItems")
    if not isinstance(items, list):
        raise ValueError("usageItems missing")

    total = 0
    matched = False
    for item in items:
        if not isinstance(item, Mapping):
            continue
        quantity = _usage_item_quantity(item)
        if quantity is None:
            continue
        total += quantity
        matched = True

    if not matched:
        raise ValueError("usage quantity missing")
    return total


def _build_usage_url(account: CopilotAccountConfig) -> tuple[str, str]:
    year, month = _current_month_utc()
    params: dict[str, str | int] = {"year": year, "month": month}

    if account.kind == "company" and account.enterprise:
        params["user"] = account.account_id
        path = f"/enterprises/{account.enterprise}/settings/billing/premium_request/usage"
        source = "github_enterprise_billing"
    elif account.kind == "company" and account.org:
        params["user"] = account.account_id
        path = f"/organizations/{account.org}/settings/billing/premium_request/usage"
        source = "github_org_billing"
    elif account.kind == "personal":
        path = f"/users/{account.account_id}/settings/billing/premium_request/usage"
        source = "github_user_billing"
    else:
        raise ValueError("company Copilot account requires org or enterprise")

    return f"{_GITHUB_API_ROOT}{path}?{urlencode(params)}", source


def _fetch_account_usage(account: CopilotAccountConfig) -> tuple[int, str]:
    url, source = _build_usage_url(account)
    token = _get_github_token(account.account_id)
    payload = _fetch_json(
        url,
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return _extract_usage_items_total(payload), source


def _fetch_copilot_quota(account: CopilotAccountConfig) -> tuple[int | None, bool]:
    """Return (percent_used, unlimited) from the Copilot plan-quota endpoint.

    `quota_snapshots.premium_interactions` carries `percent_remaining` (and an
    `unlimited` flag for business/enterprise seats). This is the same source the
    Copilot CLI statusline shows, and it is a single cheap HTTP GET — no local
    log scanning — so it is safe to call on every refresh."""
    token = _get_github_token(account.account_id)
    payload = _fetch_json(
        _COPILOT_USER_URL,
        {
            "Accept": "application/json",
            "Authorization": f"token {token}",
        },
    )
    snapshots = payload.get("quota_snapshots")
    if not isinstance(snapshots, Mapping):
        raise ValueError("quota_snapshots missing")
    premium = snapshots.get("premium_interactions")
    if not isinstance(premium, Mapping):
        raise ValueError("premium_interactions missing")
    if premium.get("unlimited"):
        return None, True
    raw_remaining = premium.get("percent_remaining")
    if raw_remaining is None:
        raise ValueError("percent_remaining missing")
    percent_used = max(0, min(100, int(round(100 - float(raw_remaining)))))
    return percent_used, False


def _get_active_github_login() -> str | None:
    try:
        completed = subprocess.run(
            ["gh", "auth", "status"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    current_account: str | None = None
    for line in output.splitlines():
        matched = _ACCOUNT_RE.search(line)
        if matched:
            current_account = matched.group(1)
        if "Active account: true" in line and current_account:
            return current_account
    return None


def _parse_event_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_month(payload: Mapping[str, Any]) -> tuple[int, int] | None:
    for key in ("timestamp", "created_at"):
        parsed = _parse_event_timestamp(payload.get(key))
        if parsed is not None:
            return parsed.year, parsed.month

    data = payload.get("data")
    if isinstance(data, Mapping):
        for key in ("timestamp", "created_at"):
            parsed = _parse_event_timestamp(data.get(key))
            if parsed is not None:
                return parsed.year, parsed.month

    return None


def _read_local_observed_metrics(year: int | None = None, month: int | None = None) -> tuple[int, int]:
    root = paths.copilot_session_state_root()
    if not root.exists():
        return 0, 0

    premium_total = 0
    total_nano_aiu = 0
    should_filter_month = year is not None and month is not None
    # When scoped to a month, a file last modified before that month cannot hold
    # any of its events — skip it by mtime so the scan never touches the huge
    # archived logs from earlier months. Also skip any single file above the
    # size cap. Together these bound memory/time so this fallback can't OOM the
    # host the way the original unbounded scan did.
    min_mtime: float | None = None
    if should_filter_month:
        min_mtime = datetime(year, month, 1, tzinfo=timezone.utc).timestamp()
    for event_path in root.rglob("events.jsonl"):
        try:
            stat_result = event_path.stat()
        except OSError:
            continue
        if min_mtime is not None and stat_result.st_mtime < min_mtime:
            continue
        if stat_result.st_size > _COPILOT_EVENT_FILE_MAX_BYTES:
            continue
        try:
            with event_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") != "session.shutdown":
                        continue
                    if should_filter_month and _event_month(payload) != (year, month):
                        continue
                    data = payload.get("data")
                    if not isinstance(data, dict):
                        continue
                    try:
                        premium_total += int(data.get("totalPremiumRequests") or 0)
                    except (TypeError, ValueError):
                        pass
                    try:
                        total_nano_aiu += int(data.get("totalNanoAiu") or 0)
                    except (TypeError, ValueError):
                        pass
        except OSError:
            continue
    return premium_total, round(total_nano_aiu / 1_000_000_000)


def _read_local_observed_total(year: int | None = None, month: int | None = None) -> int:
    premium_total, _ = _read_local_observed_metrics(year=year, month=month)
    return premium_total


def _read_local_observed_aiu(year: int | None = None, month: int | None = None) -> int:
    """Sum Copilot AI Credits (AIU) from local session-shutdown events.

    Copilot CLI pre-computes the per-session credits as `data.totalNanoAiu`
    (1 AI credit = 1e9 nanoAiu = $0.01); we just sum and divide. AIU only exists
    after the 2026-06-01 usage-based-billing migration (older months are 0)."""
    _, aiu_total = _read_local_observed_metrics(year=year, month=month)
    return aiu_total


# Attribution is metric-based — premium-request → the configured kind='personal' account,
# AIU → the configured kind='company' account (config-driven; events.jsonl has no
# logged-in account so we don't gate on gh login).


def _resolve_attribution_accounts(config: CostConfig) -> tuple[str | None, str | None]:
    """premium-request -> first kind=='personal' account id; AIU -> first kind=='company' account id."""
    premium = next(
        (
            a.account_id
            for a in config.copilot_accounts
            if a.enabled and a.kind == "personal"
        ),
        None,
    )
    aiu = next(
        (
            a.account_id
            for a in config.copilot_accounts
            if a.enabled and a.kind == "company"
        ),
        None,
    )
    return premium, aiu


def _collect_local_observed_usage(
    premium_account: str | None,
    aiu_account: str | None,
    allowed_accounts: set[str] | None = None,
) -> dict[str, int]:
    year, month = _current_month_utc()
    usage: dict[str, int] = {}
    premium, aiu = _read_local_observed_metrics(year=year, month=month)
    if premium > 0 and premium_account:
        usage[premium_account] = premium
    if aiu > 0 and aiu_account:
        usage[aiu_account] = aiu
    if allowed_accounts is not None:
        usage = {key: value for key, value in usage.items() if key in allowed_accounts}
    return usage


def collect_copilot(
    config: CostConfig,
    *,
    fetcher: CopilotFetcher | None = None,
    local_observed: Mapping[str, int] | None = None,
) -> ProviderSnapshot:
    enabled_accounts = tuple(account for account in config.copilot_accounts if account.enabled)
    if not enabled_accounts:
        return ProviderSnapshot(source_status="unknown", source="unknown", accounts=())

    accounts: list[CopilotAccountUsage] = []
    has_fresh = False
    has_estimated = False
    resolved_local_observed = local_observed
    allowed_account_ids = {account.account_id for account in enabled_accounts}

    for account in enabled_accounts:
        # Primary (production): the plan-quota endpoint — the % the Copilot CLI
        # statusline shows, via one cheap HTTP GET and no local log scanning.
        # An injected `fetcher` (tests / legacy billing override) bypasses this.
        if fetcher is None:
            try:
                percent_used, unlimited = _fetch_copilot_quota(account)
            except Exception:
                pass
            else:
                accounts.append(
                    CopilotAccountUsage(
                        account_id=account.account_id,
                        label=account.label,
                        kind=account.kind,
                        used_requests=None,
                        monthly_allowance=account.monthly_allowance,
                        source="github_copilot_quota",
                        percent_used=percent_used,
                        unlimited=unlimited,
                    )
                )
                has_fresh = True
                continue

        # Fallback: premium-request billing count (often 403 for team plans).
        billing_fetcher = fetcher or _fetch_account_usage
        try:
            used_requests, source = billing_fetcher(account)
        except Exception:
            used_requests = source = None
        else:
            accounts.append(
                CopilotAccountUsage(
                    account_id=account.account_id,
                    label=account.label,
                    kind=account.kind,
                    used_requests=int(used_requests),
                    monthly_allowance=account.monthly_allowance,
                    source=str(source),
                )
            )
            has_fresh = True
            continue

        if resolved_local_observed is None and fetcher is None:
            premium_account, aiu_account = _resolve_attribution_accounts(config)
            resolved_local_observed = _collect_local_observed_usage(premium_account, aiu_account, allowed_account_ids)

        if resolved_local_observed is not None and account.account_id in resolved_local_observed:
            accounts.append(
                CopilotAccountUsage(
                    account_id=account.account_id,
                    label=account.label,
                    kind=account.kind,
                    used_requests=int(resolved_local_observed[account.account_id]),
                    monthly_allowance=account.monthly_allowance,
                    source="local_observed",
                )
            )
            has_estimated = True
            continue

        accounts.append(_unknown_account(account))

    if has_fresh:
        source_status = "fresh"
    elif has_estimated:
        source_status = "estimated"
    else:
        source_status = "unknown"
    provider_source = "api" if has_fresh else "local_observed" if has_estimated else "unknown"

    return ProviderSnapshot(
        source_status=source_status,
        source=provider_source,
        accounts=tuple(accounts),
    )


def collect_all(config: CostConfig) -> dict[str, ProviderSnapshot]:
    providers: dict[str, ProviderSnapshot] = {}
    if config.codex.enabled:
        providers["cdx"] = collect_codex(
            enabled=config.codex.enabled,
            auth_path=config.codex.auth_path,
            usage_url=config.codex.usage_url,
            max_age_seconds=config.codex.max_age_seconds,
            local_fallback=config.codex.local_fallback,
            timezone=config.timezone,
        )
    if config.claude.enabled:
        providers["cc"] = collect_claude(
            statusline_sidecar=config.claude.statusline_sidecar,
            max_age_seconds=config.claude.max_age_seconds,
            local_fallback=config.claude.local_fallback,
            timezone=config.timezone,
        )
    copilot = collect_copilot(config)
    if copilot.accounts:
        providers["cpt"] = copilot
    if config.agy.effective_enabled:
        agy = collect_agy(config.agy, timezone_name=config.timezone)
        if agy is not None:
            providers["agy"] = agy
    return providers


def _provider_has_data(provider: ProviderSnapshot) -> bool:
    if provider.accounts:
        return any(
            account.percent_used is not None
            or account.used_requests is not None
            or account.unlimited
            for account in provider.accounts
        )
    return any(window.used_percent is not None for window in provider.windows.values())


def carry_forward_degraded(
    new_providers: dict[str, ProviderSnapshot],
    old_providers: Mapping[str, ProviderSnapshot],
    *,
    skip: Iterable[str] = (),
) -> dict[str, ProviderSnapshot]:
    """Keep showing the previous values when a provider returns nothing usable.

    When a fetch fails this cycle (e.g. Claude sidecar gone stale, Copilot quota
    network blip), reuse the previous snapshot's values — marked ``stale`` so the
    footer tints them — instead of dropping to ``--``. Fresh data the next cycle
    replaces them and clears the stale marker.

    Providers named in ``skip`` manage their own stale supply and are passed
    through untouched: agy keeps a throttled sidecar with ``stale_max_age_seconds``
    (#353), so resurrecting its cached windows here would bypass that age cap and
    the ``exp`` rendering, showing a frozen reset clock indefinitely."""
    skipped = set(skip)
    result: dict[str, ProviderSnapshot] = {}
    for name, provider in new_providers.items():
        old = old_providers.get(name)
        if (
            name not in skipped
            and old is not None
            and not _provider_has_data(provider)
            and _provider_has_data(old)
        ):
            result[name] = ProviderSnapshot(
                source_status="stale",
                source=old.source,
                windows=dict(old.windows),
                accounts=tuple(old.accounts),
                note=old.note,
                label=old.label,
            )
        else:
            result[name] = provider
    return result
