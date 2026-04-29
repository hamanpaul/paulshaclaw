from __future__ import annotations

from typing import Callable, Mapping

from paulshaclaw.cost.config import CopilotAccountConfig, CostConfig
from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot

CopilotFetcher = Callable[[CopilotAccountConfig], tuple[int, str]]


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

    for account in config.copilot_accounts:
        if fetcher is not None:
            try:
                used_requests, source = fetcher(account)
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
            except Exception:
                pass

        if local_observed is not None and account.account_id in local_observed:
            accounts.append(
                CopilotAccountUsage(
                    account_id=account.account_id,
                    label=account.label,
                    kind=account.kind,
                    used_requests=int(local_observed[account.account_id]),
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
