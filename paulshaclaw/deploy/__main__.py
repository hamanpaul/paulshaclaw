from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .installer import DeploymentVerificationError, install_deployment, verify_deployment
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
    if args.command == "install" and args.apply:
        payload: dict[str, object] = install_deployment(
            instance_name=args.instance,
            root_dir=args.root_dir,
        ).as_dict()
        if args.verify:
            payload["verify"] = verify_deployment(instance_name=args.instance).as_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "install" and args.verify:
        try:
            payload = verify_deployment(instance_name=args.instance).as_dict()
        except DeploymentVerificationError as error:
            print(str(error), file=sys.stderr)
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    plan = build_command_plan(
        args.command,
        instance_name=args.instance,
        root_dir=args.root_dir,
    )
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
