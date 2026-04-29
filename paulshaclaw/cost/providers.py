from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from paulshaclaw.cost.config import CopilotAccountConfig, CostConfig
from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot

CopilotFetcher = Callable[[CopilotAccountConfig], tuple[int, str]]
_GITHUB_API_ROOT = "https://api.github.com"
_ACCOUNT_RE = re.compile(r"account\s+([A-Za-z0-9-]+)")


def collect_codex() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="trusted quota windows unavailable",
    )


def collect_claude() -> ProviderSnapshot:
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


def _read_local_observed_total() -> int:
    root = Path.home() / ".copilot" / "session-state"
    if not root.exists():
        return 0

    total = 0
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
    total = _read_local_observed_total()
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
    has_stale = False
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
            has_stale = True
            continue

        accounts.append(_unknown_account(account))

    if has_fresh:
        source_status = "fresh"
    elif has_stale:
        source_status = "stale"
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
