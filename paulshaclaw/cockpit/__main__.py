from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 11 operator cockpit")
    parser.add_argument("--cockpit-pane", required=False, help="tmux pane id hosting the cockpit")
    parser.add_argument("--once", action="store_true", help="initialize and exit without entering the UI")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
