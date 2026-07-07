from __future__ import annotations

import argparse
import json
from typing import Sequence

from .installer import run_install
from .planner import build_command_plan


SUPPORTED_COMMANDS = ("install", "upgrade", "uninstall")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.deploy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in SUPPORTED_COMMANDS:
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--instance", default="paulshaclaw")
        subparser.add_argument("--root-dir", required=True)
        if command == "install":
            subparser.add_argument("--apply", action="store_true")
            subparser.add_argument("--verify", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "install" and (args.apply or args.verify):
        report, exit_code = run_install(
            instance_name=args.instance,
            root_dir=args.root_dir,
            apply=args.apply,
            verify=args.verify,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    plan = build_command_plan(
        args.command,
        instance_name=args.instance,
        root_dir=args.root_dir,
    )
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
