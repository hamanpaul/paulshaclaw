from __future__ import annotations

import argparse

from .actions import LayoutActionService
from .app import CockpitApp
from .models import PaneRecord


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 11 operator cockpit")
    parser.add_argument("--cockpit-pane", required=True, help="tmux pane id hosting the cockpit")
    parser.add_argument("--once", action="store_true", help="initialize and exit without entering the UI")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.once:
        return 0
    app = CockpitApp.from_snapshot(
        panes=(PaneRecord(args.cockpit_pane, "cockpit", "python", 0, 0, 1, 1, False, ()),),
        cockpit_pane_id=args.cockpit_pane,
        jobs_by_pane={},
        actions=LayoutActionService(),
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
