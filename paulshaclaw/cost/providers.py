from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from paulshaclaw.cost.config import CopilotAccountConfig, CostConfig
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


def _unknown_codex() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="trusted quota windows unavailable",
    )


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

    reset_at = _parse_epoch(
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


def _file_is_fresh(path: Path, max_age_seconds: int) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return time.time() - stat.st_mtime <= max_age_seconds


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


def _claude_local_token_total(claude_home: Path) -> int:
    projects = claude_home / "projects"
    if not projects.exists():
        return 0

    total = 0
    for session_path in projects.rglob("*.jsonl"):
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


def _codex_local_token_total(codex_home: Path) -> int:
    sessions = codex_home / "sessions"
    if not sessions.exists():
        return 0

    observed = 0
    for session_path in sessions.rglob("*.jsonl"):
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
    resolved_auth_path = auth_path or Path("~/.codex/auth.json").expanduser()
    resolved_fetcher = fetcher or _fetch_codex_usage
    resolved_token_reader = token_reader or _read_codex_token

    # Prefer the trusted quota Codex already wrote locally (correct, no network);
    # the live usage endpoint is often 403 for non-OAuth/team plans.
    local_windows = _codex_local_rate_limits(codex_home or Path("~/.codex").expanduser(), resolved_now)
    if local_windows:
        return ProviderSnapshot(source_status="fresh", windows=local_windows)

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
            windows={"five_hour": five_hour, "weekly": weekly},
        )
    except Exception:
        pass

    if local_fallback:
        tokens = _codex_local_token_total(codex_home or Path("~/.codex").expanduser())
        if tokens > 0:
            return ProviderSnapshot(
                source_status="estimated",
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
    sidecar = statusline_sidecar or Path("~/.agents/state/cost/claude_rate_limits.json").expanduser()
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
                return ProviderSnapshot(source_status="fresh", windows=windows)

    if local_fallback:
        tokens = _claude_local_token_total(claude_home or Path("~/.claude").expanduser())
        if tokens > 0:
            return ProviderSnapshot(
                source_status="estimated",
                windows={"five_hour": _estimated_window_from_tokens(tokens)},
                note="local Claude Code token estimate",
            )

    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="credentials or trusted quota source unavailable",
    )


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
    root = Path.home() / ".copilot" / "session-state"
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


# Attribution is metric-based per the operator's rule (see the project-usage-assess
# skill): premium requests -> hamanpaul, AI credits (AIU) -> paulc-arc. events.jsonl
# does not record the logged-in account, so we do NOT gate on the active gh login.
_COPILOT_PREMIUM_ACCOUNT = "hamanpaul"
_COPILOT_AIU_ACCOUNT = "paulc-arc"


def _collect_local_observed_usage(allowed_accounts: set[str] | None = None) -> dict[str, int]:
    year, month = _current_month_utc()
    usage: dict[str, int] = {}
    premium, aiu = _read_local_observed_metrics(year=year, month=month)
    if premium > 0:
        usage[_COPILOT_PREMIUM_ACCOUNT] = premium
    if aiu > 0:
        usage[_COPILOT_AIU_ACCOUNT] = aiu
    if allowed_accounts is not None:
        usage = {key: value for key, value in usage.items() if key in allowed_accounts}
    return usage


def collect_copilot(
    config: CostConfig,
    *,
    fetcher: CopilotFetcher | None = None,
    local_observed: Mapping[str, int] | None = None,
) -> ProviderSnapshot:
    if not config.copilot_accounts:
        return ProviderSnapshot(source_status="unknown", accounts=())

    accounts: list[CopilotAccountUsage] = []
    has_fresh = False
    has_estimated = False
    resolved_local_observed = local_observed
    allowed_account_ids = {account.account_id for account in config.copilot_accounts}

    for account in config.copilot_accounts:
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
            resolved_local_observed = _collect_local_observed_usage(allowed_account_ids)

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

    return ProviderSnapshot(source_status=source_status, accounts=tuple(accounts))


def collect_all(config: CostConfig) -> dict[str, ProviderSnapshot]:
    providers = {
        "cdx": collect_codex(
            enabled=config.codex.enabled,
            auth_path=config.codex.auth_path,
            usage_url=config.codex.usage_url,
            max_age_seconds=config.codex.max_age_seconds,
            local_fallback=config.codex.local_fallback,
            timezone=config.timezone,
        ),
        "cc": collect_claude(
            statusline_sidecar=config.claude.statusline_sidecar,
            max_age_seconds=config.claude.max_age_seconds,
            local_fallback=config.claude.local_fallback,
            timezone=config.timezone,
        ),
    }
    copilot = collect_copilot(config)
    if copilot.accounts:
        providers["cpt"] = copilot
    return providers
