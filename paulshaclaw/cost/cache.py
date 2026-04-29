from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow

_DEFAULT_TIMEZONE = "Asia/Taipei"
_TOKEN_HINTS = ("token", "secret", "bearer ", "ghp_", "github_pat_")


def _resolve_timezone(timezone: str) -> tuple[str, ZoneInfo]:
    try:
        return timezone, ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return _DEFAULT_TIMEZONE, ZoneInfo(_DEFAULT_TIMEZONE)


def build_snapshot(
    *,
    timezone: str,
    providers: dict[str, ProviderSnapshot],
    cache_status: str = "fresh",
) -> CostSnapshot:
    resolved_timezone, zone = _resolve_timezone(timezone)
    return CostSnapshot(
        generated_at=datetime.now(zone),
        timezone=resolved_timezone,
        cache_status=str(cache_status or "fresh"),
        providers=dict(providers),
    )


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_window(raw: Any) -> UsageWindow:
    if not isinstance(raw, dict):
        return UsageWindow(used_percent=None, reset_at=None, display_reset=None)

    used_percent = raw.get("used_percent")
    if used_percent is not None:
        try:
            used_percent = int(used_percent)
        except (TypeError, ValueError):
            used_percent = None

    display_reset = raw.get("display_reset")
    if display_reset is not None and not isinstance(display_reset, str):
        display_reset = str(display_reset)

    return UsageWindow(
        used_percent=used_percent,
        reset_at=_parse_dt(raw.get("reset_at")),
        display_reset=display_reset,
    )


def _load_account(raw: Any) -> CopilotAccountUsage | None:
    if not isinstance(raw, dict):
        return None

    account_id = raw.get("id")
    if not isinstance(account_id, str) or not account_id:
        return None

    label = raw.get("label")
    if not isinstance(label, str) or not label:
        label = account_id

    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind:
        kind = "personal"

    used_requests = raw.get("used_requests")
    if used_requests is not None:
        try:
            used_requests = int(used_requests)
        except (TypeError, ValueError):
            used_requests = None

    monthly_allowance = raw.get("monthly_allowance")
    if monthly_allowance is not None:
        try:
            monthly_allowance = int(monthly_allowance)
        except (TypeError, ValueError):
            monthly_allowance = None

    source = raw.get("source")
    if not isinstance(source, str) or not source:
        source = "unknown"

    return CopilotAccountUsage(
        account_id=account_id,
        label=label,
        kind=kind,
        used_requests=used_requests,
        monthly_allowance=monthly_allowance,
        source=source,
    )


def _safe_note(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    note = value.strip()
    if not note:
        return None
    lowered = note.lower()
    if any(hint in lowered for hint in _TOKEN_HINTS):
        return None
    return note


def _load_provider(raw: Any) -> ProviderSnapshot:
    if not isinstance(raw, dict):
        return ProviderSnapshot(source_status="unknown", windows={})

    source_status = raw.get("source_status")
    if not isinstance(source_status, str) or not source_status:
        source_status = "unknown"

    windows_raw = raw.get("windows")
    windows: dict[str, UsageWindow] = {}
    if isinstance(windows_raw, dict):
        for name, window_raw in windows_raw.items():
            if isinstance(name, str) and name:
                windows[name] = _load_window(window_raw)

    accounts_raw = raw.get("accounts")
    accounts: list[CopilotAccountUsage] = []
    if isinstance(accounts_raw, list):
        for account_raw in accounts_raw:
            account = _load_account(account_raw)
            if account is not None:
                accounts.append(account)

    return ProviderSnapshot(
        source_status=source_status,
        windows=windows,
        accounts=tuple(accounts),
        note=_safe_note(raw.get("note")),
    )


def load_snapshot_payload(payload: Any) -> CostSnapshot:
    if not isinstance(payload, dict):
        payload = {}

    timezone = payload.get("timezone")
    if not isinstance(timezone, str) or not timezone:
        timezone = _DEFAULT_TIMEZONE
    resolved_timezone, zone = _resolve_timezone(timezone)

    generated_at = _parse_dt(payload.get("generated_at")) or datetime.now(zone)
    cache_status = payload.get("cache_status")
    if not isinstance(cache_status, str) or not cache_status:
        cache_status = "fresh"

    providers_raw = payload.get("providers")
    providers: dict[str, ProviderSnapshot] = {}
    if isinstance(providers_raw, dict):
        for name, provider_raw in providers_raw.items():
            if isinstance(name, str) and name:
                providers[name] = _load_provider(provider_raw)

    return CostSnapshot(
        generated_at=generated_at,
        timezone=resolved_timezone,
        cache_status=cache_status,
        providers=providers,
    )


class SnapshotCache:
    def __init__(self, cache_dir: Path, *, ttl_seconds: int) -> None:
        self.cache_dir = cache_dir
        self.ttl_seconds = int(ttl_seconds)
        self.snapshot_path = self.cache_dir / "snapshot.json"
        self.lock_path = self.cache_dir / "snapshot.lock"

    def read_if_fresh(self) -> CostSnapshot | None:
        if not self.snapshot_path.exists():
            return None
        if self.ttl_seconds <= 0:
            return None
        age_seconds = time.time() - self.snapshot_path.stat().st_mtime
        if age_seconds >= self.ttl_seconds:
            return None
        return self.read_stale()

    def read_stale(self) -> CostSnapshot | None:
        if not self.snapshot_path.exists():
            return None
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return load_snapshot_payload(payload)

    def write(self, snapshot: CostSnapshot) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(
            json.dumps(snapshot.to_jsonable(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @contextmanager
    def lock(self) -> Iterator[bool]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fd: int | None = None
        try:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                yield False
                return
            yield True
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass
