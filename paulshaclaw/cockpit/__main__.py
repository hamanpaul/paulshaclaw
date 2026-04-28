from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .actions import LayoutActionService
from .app import CockpitApp
from .artifacts import ArtifactAdapter
from .tmux import TmuxClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 11 operator cockpit")
    parser.add_argument("--cockpit-pane", required=True, help="tmux pane id hosting the cockpit")
    parser.add_argument(
        "--coordinator-jobs-dir",
        type=Path,
        default=None,
        help="override coordinator jobs directory",
    )
    parser.add_argument("--once", action="store_true", help="initialize and exit without entering the UI")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tmux_client = TmuxClient()
    panes = tmux_client.list_panes(cockpit_pane_id=args.cockpit_pane)
    jobs_by_pane = ArtifactAdapter(coordinator_jobs_dir=args.coordinator_jobs_dir).load_jobs_by_pane()
    cockpit_pane = next((pane for pane in panes if pane.pane_id == args.cockpit_pane), None)
    if cockpit_pane is None:
        print(f"cockpit pane not found: {args.cockpit_pane}", file=sys.stderr)
        return 1
    if args.once:
        return 0
    app = CockpitApp.from_snapshot(
        panes=panes,
        cockpit_pane_id=args.cockpit_pane,
        cockpit_session_name=cockpit_pane.session_name,
        jobs_by_pane=jobs_by_pane,
        actions=LayoutActionService(),
        pane_loader=tmux_client.list_panes,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
