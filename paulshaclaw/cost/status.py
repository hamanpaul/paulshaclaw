from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .__main__ import build_current_snapshot
from .cache import SnapshotCache
from .config import load_cost_config
from .formatter import format_footer

_FALLBACK_LINE = "cdx 5h:-- wk:--  cc 5h:-- wk:--"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw.cost.status",
        description="Stage 8 tmux footer status",
    )
    parser.add_argument("--config", default=None, help="path to paulshaclaw.yaml")
    parser.add_argument("--plain", action="store_true", help="disable tmux formatting")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else None

    try:
        config = load_cost_config(config_path=config_path)
        cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
        snapshot = cache.read_if_fresh()
        if snapshot is None:
            with cache.lock() as acquired:
                if acquired:
                    snapshot = build_current_snapshot(config_path)
                else:
                    snapshot = cache.read_stale()
        if snapshot is None:
            snapshot = build_current_snapshot(config_path)
        print(format_footer(snapshot, use_tmux_style=not args.plain))
        return 0
    except Exception as error:
        print(_FALLBACK_LINE)
        print(f"stage8 cost status degraded: {error}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
