from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .__main__ import build_current_snapshot
from .cache import SnapshotCache
from .config import load_cost_config
from .formatter import format_footer
from .models import CostSnapshot, ProviderSnapshot

_FALLBACK_LINE = "cdx 5h:-- wk:--  cc 5h:-- wk:--"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw.cost.status",
        description="Stage 8 tmux footer status",
    )
    parser.add_argument("--config", default=None, help="path to paulshaclaw.yaml")
    parser.add_argument("--plain", action="store_true", help="disable tmux formatting")
    return parser


def _mark_snapshot_stale(snapshot: CostSnapshot) -> CostSnapshot:
    providers = {
        name: ProviderSnapshot(
            source_status="stale" if provider.source_status == "fresh" else provider.source_status,
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else None
    degraded_error: Exception | None = None

    try:
        config = load_cost_config(config_path=config_path)
        cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
        snapshot = cache.read_if_fresh()
        if snapshot is None:
            previous_snapshot = cache.read_stale()
            with cache.lock() as acquired:
                if acquired:
                    try:
                        snapshot = build_current_snapshot(config_path)
                    except Exception as error:
                        if previous_snapshot is None:
                            raise
                        degraded_error = error
                        snapshot = _mark_snapshot_stale(previous_snapshot)
                else:
                    snapshot = (
                        _mark_snapshot_stale(previous_snapshot)
                        if previous_snapshot is not None
                        else None
                    )
        if snapshot is None:
            snapshot = build_current_snapshot(config_path)
        print(format_footer(snapshot, use_tmux_style=not args.plain))
        if degraded_error is not None:
            print(f"stage8 cost status degraded: {degraded_error}", file=sys.stderr)
        return 0
    except Exception as error:
        print(_FALLBACK_LINE)
        print(f"stage8 cost status degraded: {error}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
