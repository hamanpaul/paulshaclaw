from __future__ import annotations

import argparse
import json
from typing import Sequence

from .planner import build_command_plan


SUPPORTED_COMMANDS = ("install", "upgrade", "uninstall")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.deploy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in SUPPORTED_COMMANDS:
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--instance", default="paulshaclaw")
        subparser.add_argument("--root-dir", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    plan = build_command_plan(
        args.command,
        instance_name=args.instance,
        root_dir=args.root_dir,
    )
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
