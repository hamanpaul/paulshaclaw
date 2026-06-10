from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cache import SnapshotCache, build_snapshot
from .config import load_cost_config
from .providers import carry_forward_degraded, collect_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw.cost",
        description="Stage 8 Cost Snapshot",
    )
    parser.add_argument("--config", default=None, help="path to paulshaclaw.yaml")
    parser.add_argument("--once", action="store_true", help="build one snapshot and print JSON")
    return parser


def build_current_snapshot(config_path: Path | None = None):
    config = load_cost_config(config_path=config_path)
    providers = collect_all(config)
    cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
    # Carry the previous values forward for any provider that came back empty,
    # so a transient fetch failure shows kept (stale) numbers instead of `--`.
    previous = cache.read_stale()
    if previous is not None:
        providers = carry_forward_degraded(providers, previous.providers)
    snapshot = build_snapshot(timezone=config.timezone, providers=providers)
    cache.write(snapshot)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.once:
        print("錯誤: Stage 8 cost CLI requires --once", file=sys.stderr)
        return 1

    config_path = Path(args.config) if args.config else None
    try:
        snapshot = build_current_snapshot(config_path)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1

    print(json.dumps(snapshot.to_jsonable(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
