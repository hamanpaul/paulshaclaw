from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UsageWindow:
    used_percent: int | None
    reset_at: datetime | None
    display_reset: str | None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "used_percent": self.used_percent,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "display_reset": self.display_reset,
        }


@dataclass(frozen=True)
class CopilotAccountUsage:
    account_id: str
    label: str
    kind: str
    used_requests: int | None
    monthly_allowance: int | None
    source: str
    # Plan-quota view (preferred footer display): the % of the monthly premium
    # quota already consumed, mirroring what the Copilot CLI statusline shows.
    # `unlimited` flags business/enterprise seats whose premium quota is uncapped.
    percent_used: int | None = None
    unlimited: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.account_id,
            "label": self.label,
            "kind": self.kind,
            "used_requests": self.used_requests,
            "monthly_allowance": self.monthly_allowance,
            "source": self.source,
        }
        if self.percent_used is not None:
            payload["percent_used"] = self.percent_used
        if self.unlimited:
            payload["unlimited"] = True
        return payload


@dataclass(frozen=True)
class ProviderSnapshot:
    source_status: str
    windows: dict[str, UsageWindow] = field(default_factory=dict)
    accounts: tuple[CopilotAccountUsage, ...] = ()
    note: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source_status": self.source_status}
        if self.windows:
            payload["windows"] = {
                name: window.to_jsonable() for name, window in self.windows.items()
            }
        if self.accounts:
            payload["accounts"] = [account.to_jsonable() for account in self.accounts]
        if self.note:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True)
class CostSnapshot:
    generated_at: datetime
    timezone: str
    cache_status: str
    providers: dict[str, ProviderSnapshot]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "timezone": self.timezone,
            "cache_status": self.cache_status,
            "providers": {
                name: provider.to_jsonable()
                for name, provider in self.providers.items()
            },
        }
