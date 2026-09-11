from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .__main__ import build_current_snapshot
from .cache import SnapshotCache, build_snapshot
from .config import load_cost_config
from .formatter import format_footer
from .models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot

_FALLBACK_LINE = "cdx 5h:-- wk:-- | cc 5h:-- wk:--"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw.cost.status",
        description="Stage 8 tmux footer status",
    )
    parser.add_argument("--config", default=None, help="path to paulshaclaw.yaml")
    parser.add_argument("--plain", action="store_true", help="disable tmux formatting")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="render only cached/degraded data; do not rebuild the snapshot",
    )
    return parser


def _mark_snapshot_stale(snapshot: CostSnapshot) -> CostSnapshot:
    providers = {
        name: ProviderSnapshot(
            source_status="stale" if provider.source_status == "fresh" else provider.source_status,
            source=provider.source,
            windows=dict(provider.windows),
            accounts=tuple(provider.accounts),
            note=provider.note,
        )
        for name, provider in snapshot.providers.items()
    }
    return CostSnapshot(
        generated_at=snapshot.generated_at,
        timezone=snapshot.timezone,
        cache_status="stale",
        providers=providers,
    )


def _build_degraded_snapshot(config) -> CostSnapshot:
    copilot_accounts = tuple(
        CopilotAccountUsage(
            account_id=account.account_id,
            label=account.label,
            kind=account.kind,
            used_requests=None,
            monthly_allowance=account.monthly_allowance,
            source="unknown",
        )
        for account in getattr(config, "copilot_accounts", ())
        if getattr(account, "enabled", True)
    )
    providers = {}
    codex = getattr(config, "codex", None)
    if getattr(codex, "enabled", True):
        providers["cdx"] = ProviderSnapshot(source_status="unknown", source="unknown", windows={})
    claude = getattr(config, "claude", None)
    if getattr(claude, "enabled", True):
        providers["cc"] = ProviderSnapshot(source_status="unknown", source="unknown", windows={})
    if copilot_accounts:
        providers["cpt"] = ProviderSnapshot(source_status="unknown", source="unknown", accounts=copilot_accounts)
    agy = getattr(config, "agy", None)
    if getattr(agy, "enabled", False):
        providers["agy"] = ProviderSnapshot(
            source_status="unknown",
            source="unknown",
            accounts=(),
            note='source="unknown"',
        )

    return build_snapshot(
        timezone=getattr(config, "timezone", "Asia/Taipei"),
        cache_status="stale",
        providers=providers,
    )


def _filter_snapshot_by_enabled(snapshot: CostSnapshot, config) -> CostSnapshot:
    providers = dict(snapshot.providers)
    changed = False

    if not getattr(getattr(config, "codex", None), "enabled", True) and "cdx" in providers:
        providers.pop("cdx", None)
        changed = True
    if not getattr(getattr(config, "claude", None), "enabled", True) and "cc" in providers:
        providers.pop("cc", None)
        changed = True
    if not getattr(getattr(config, "agy", None), "enabled", False) and "agy" in providers:
        providers.pop("agy", None)
        changed = True

    copilot_provider = providers.get("cpt")
    copilot_accounts = getattr(config, "copilot_accounts", None)
    if copilot_provider is not None and copilot_accounts is not None:
        enabled_account_ids = {
            account.account_id
            for account in copilot_accounts
            if getattr(account, "enabled", True)
        }
        accounts = tuple(
            account
            for account in copilot_provider.accounts
            if account.account_id in enabled_account_ids
        )
        if accounts != copilot_provider.accounts:
            changed = True
            if accounts:
                providers["cpt"] = ProviderSnapshot(
                    source_status=copilot_provider.source_status,
                    source=copilot_provider.source,
                    windows=dict(copilot_provider.windows),
                    accounts=accounts,
                    note=copilot_provider.note,
                )
            else:
                providers.pop("cpt", None)
        elif not accounts and not enabled_account_ids:
            providers.pop("cpt", None)
            changed = True

    if not changed:
        return snapshot
    return CostSnapshot(
        generated_at=snapshot.generated_at,
        timezone=snapshot.timezone,
        cache_status=snapshot.cache_status,
        providers=providers,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else None
    degraded_error: Exception | None = None
    previous_snapshot: CostSnapshot | None = None

    try:
        config = load_cost_config(config_path=config_path)
    except Exception as error:
        print(_FALLBACK_LINE)
        print(f"stage8 cost status degraded: {error}", file=sys.stderr)
        return 0

    try:
        cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
        snapshot = cache.read_if_fresh()
        if snapshot is None:
            previous_snapshot = cache.read_stale()
            if args.no_refresh:
                snapshot = (
                    _mark_snapshot_stale(previous_snapshot)
                    if previous_snapshot is not None
                    else _build_degraded_snapshot(config)
                )
            else:
                with cache.lock() as acquired:
                    if acquired:
                        try:
                            snapshot = build_current_snapshot(config_path)
                        except Exception as error:
                            degraded_error = error
                            snapshot = (
                                _mark_snapshot_stale(previous_snapshot)
                                if previous_snapshot is not None
                                else _build_degraded_snapshot(config)
                            )
                    else:
                        snapshot = (
                            _mark_snapshot_stale(previous_snapshot)
                            if previous_snapshot is not None
                            else _build_degraded_snapshot(config)
                        )
        if snapshot is None:
            snapshot = _build_degraded_snapshot(config) if args.no_refresh else build_current_snapshot(config_path)
    except Exception as error:
        degraded_error = error
        snapshot = (
            _mark_snapshot_stale(previous_snapshot)
            if previous_snapshot is not None
            else _build_degraded_snapshot(config)
        )

    try:
        print(format_footer(_filter_snapshot_by_enabled(snapshot, config), use_tmux_style=not args.plain))
    except Exception as error:
        print(_FALLBACK_LINE)
        print(f"stage8 cost status degraded: {error}", file=sys.stderr)
        return 0
    if degraded_error is not None:
        print(f"stage8 cost status degraded: {degraded_error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
