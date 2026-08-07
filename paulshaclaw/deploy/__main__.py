from __future__ import annotations

import argparse
import json
from typing import Sequence

from .installer import (
    ArtifactVerificationError,
    read_install_record,
    run_install,
    run_rollback,
    run_uninstall,
    run_upgrade,
)
from .planner import build_command_plan


SUPPORTED_COMMANDS = ("install", "upgrade", "uninstall", "status", "rollback")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.deploy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("install", "upgrade", "uninstall"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--instance", default="paulshaclaw")
        subparser.add_argument("--root-dir", required=True)
        subparser.add_argument("--apply", action="store_true")
        if command != "uninstall":
            subparser.add_argument("--verify", action="store_true")
        if command in ("install", "upgrade"):
            subparser.add_argument("--version", default=None, help="指定要套用的正式版本（SemVer）")
            subparser.add_argument("--artifact", default=None, help="artifact 來源（本地路徑或 URL）")
            subparser.add_argument(
                "--artifact-sha256",
                default=None,
                help="期望的 artifact SHA-256；指定後不符即 fail-closed",
            )
        if command == "uninstall":
            subparser.add_argument(
                "--purge-state",
                action="store_true",
                help="清除 state plane（預設保留）",
            )
            subparser.add_argument(
                "--purge-secret",
                action="store_true",
                help="清除 secret plane（預設保留）",
            )

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--instance", default="paulshaclaw")
    status_parser.add_argument("--root-dir", required=True)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--instance", default="paulshaclaw")
    rollback_parser.add_argument("--root-dir", required=True)
    rollback_parser.add_argument(
        "--from-command",
        default=None,
        help="指定還原來源的 command checkpoint（upgrade/uninstall）",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "install" and (args.apply or args.verify):
        try:
            report, exit_code = run_install(
                instance_name=args.instance,
                root_dir=args.root_dir,
                apply=args.apply,
                verify=args.verify,
                version=args.version,
                artifact=args.artifact,
                artifact_sha256=args.artifact_sha256,
            )
        except ArtifactVerificationError as exc:
            print(json.dumps({"command": "install", "status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    if args.command == "upgrade" and (args.apply or args.verify):
        try:
            report, exit_code = run_upgrade(
                instance_name=args.instance,
                root_dir=args.root_dir,
                apply=args.apply,
                verify=args.verify,
                version=args.version,
                artifact=args.artifact,
                artifact_sha256=args.artifact_sha256,
            )
        except ArtifactVerificationError as exc:
            print(json.dumps({"command": "upgrade", "status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    if args.command == "uninstall" and args.apply:
        report, exit_code = run_uninstall(
            instance_name=args.instance,
            root_dir=args.root_dir,
            apply=args.apply,
            purge_state=args.purge_state,
            purge_secret=args.purge_secret,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    if args.command == "status":
        record = read_install_record(instance_name=args.instance)
        print(json.dumps(record, ensure_ascii=False, indent=2) if record else "{}")
        return 0

    if args.command == "rollback":
        report, exit_code = run_rollback(
            instance_name=args.instance,
            root_dir=args.root_dir,
            command=args.from_command,
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
