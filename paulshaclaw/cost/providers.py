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
from zoneinfo import ZoneInfo

from paulshaclaw.cost.config import CopilotAccountConfig, CostConfig
from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot, UsageWindow

CopilotFetcher = Callable[[CopilotAccountConfig], tuple[int, str]]
JsonFetcher = Callable[[str, Mapping[str, str]], dict[str, Any]]
CodexTokenReader = Callable[[Path], tuple[str, str]]
_GITHUB_API_ROOT = "https://api.github.com"
_CODEX_USAGE_URL = "https://chatgpt.com/api/codex/usage"
_ACCOUNT_RE = re.compile(r"account\s+([A-Za-z0-9-]+)")


def _unknown_codex() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="trusted quota windows unavailable",
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
    access_token = payload.get("access_token")
    account_id = payload.get("account_id")
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
        raw.get("reset_at", raw.get("resetsAt")),
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
                    total_usage = payload.get("total_token_usage")
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


def collect_codex(
    *,
    enabled: bool = False,
    auth_path: Path | None = None,
    usage_url: str = _CODEX_USAGE_URL,
    local_fallback: bool = False,
    codex_home: Path | None = None,
    fetcher: JsonFetcher | None = None,
    token_reader: CodexTokenReader | None = None,
    now: datetime | None = None,
) -> ProviderSnapshot:
    if not enabled:
        return _unknown_codex()

    resolved_now = now or _now_utc().astimezone(ZoneInfo("Asia/Taipei"))
    resolved_auth_path = auth_path or Path("~/.codex/auth.json").expanduser()
    resolved_fetcher = fetcher or _fetch_codex_usage
    resolved_token_reader = token_reader or _read_codex_token

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
) -> ProviderSnapshot:
    resolved_now = now or _now_utc().astimezone(ZoneInfo("Asia/Taipei"))
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


def _get_active_github_login() -> str | None:
    completed = subprocess.run(
        ["gh", "auth", "status"],
        check=False,
        capture_output=True,
        text=True,
    )
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


def _read_local_observed_total(year: int | None = None, month: int | None = None) -> int:
    root = Path.home() / ".copilot" / "session-state"
    if not root.exists():
        return 0

    total = 0
    should_filter_month = year is not None and month is not None
    for event_path in root.rglob("events.jsonl"):
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
                    value = data.get("totalPremiumRequests")
                    try:
                        total += int(value)
                    except (TypeError, ValueError):
                        continue
        except OSError:
            continue
    return total


def _collect_local_observed_usage(allowed_accounts: set[str] | None = None) -> dict[str, int]:
    active_account = _get_active_github_login()
    if not active_account:
        return {}
    if allowed_accounts is not None and active_account not in allowed_accounts:
        return {}
    year, month = _current_month_utc()
    total = _read_local_observed_total(year=year, month=month)
    if total <= 0:
        return {}
    return {active_account: total}


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

    for account in config.copilot_accounts:
        if fetcher is not None:
            try:
                used_requests, source = fetcher(account)
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
        else:
            try:
                used_requests, source = _fetch_account_usage(account)
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
        "cdx": collect_codex(),
        "cc": collect_claude(),
    }
    copilot = collect_copilot(config)
    if copilot.accounts:
        providers["cpt"] = copilot
    return providers
