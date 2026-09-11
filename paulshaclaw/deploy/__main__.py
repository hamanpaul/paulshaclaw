from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .agents import (
    detected_agents_report,
    detect_agents,
    prepare_footer_selection,
    write_footer_config,
)
from .installer import (
    ArtifactVerificationError,
    TemplatePreflightError,
    _record_template_preflight_failure,
    preflight_templates,
    read_install_record,
    run_install,
    run_rollback,
    run_uninstall,
    run_upgrade,
)
from .planner import build_command_plan


SUPPORTED_COMMANDS = ("install", "upgrade", "uninstall", "status", "rollback")


def _attach_footer_metadata(
    payload: dict[str, object],
    *,
    detected_agents: Sequence[object],
    footer_selection: dict[str, Any],
) -> dict[str, object]:
    payload["detected_agents"] = detected_agents_report(detected_agents)
    payload["footer_selection"] = footer_selection
    return payload


def _resolve_footer_home(home_dir: str | None) -> Path | None:
    if home_dir is None:
        return None
    return Path(home_dir).expanduser()


def _emit_footer_failure(
    *,
    command: str,
    footer: str | None,
    home_dir: str | None,
    error: Exception,
) -> int:
    payload: dict[str, object] = {
        "command": command,
        "status": "failed",
        "error": str(error),
    }
    selection: dict[str, Any] = {"mode": "flag" if footer is not None else "skipped"}
    if footer is not None:
        selection["requested"] = footer
    _attach_footer_metadata(
        payload,
        detected_agents=detect_agents(home=_resolve_footer_home(home_dir)),
        footer_selection=selection,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.deploy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("install", "upgrade", "uninstall"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--instance", default="paulshaclaw")
        subparser.add_argument("--root-dir", required=True)
        subparser.add_argument(
            "--home-dir",
            default=None,
            help="家目錄根（預設走 PSC_HOME_ROOT / $HOME）；顯式指定可隔離部署落點",
        )
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
            subparser.add_argument(
                "--footer",
                default=None,
                help="footer 選擇；支援 codex,claude,copilot[:label...],agy,none",
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
    status_parser.add_argument(
        "--home-dir",
        default=None,
        help="家目錄根（預設走 PSC_HOME_ROOT / $HOME）",
    )

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--instance", default="paulshaclaw")
    rollback_parser.add_argument("--root-dir", required=True)
    rollback_parser.add_argument(
        "--home-dir",
        default=None,
        help="家目錄根（預設走 PSC_HOME_ROOT / $HOME）",
    )
    rollback_parser.add_argument(
        "--from-command",
        default=None,
        help="指定還原來源的 command checkpoint（upgrade/uninstall）",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    footer_detected: tuple[object, ...] | None = None
    footer_selection: dict[str, Any] | None = None
    selected_footer: dict[str, object] | None = None

    if args.command in ("install", "upgrade"):
        try:
            footer_detected, footer_selection, selected_footer = prepare_footer_selection(
                footer=args.footer,
                apply=bool(getattr(args, "apply", False)),
                verify=bool(getattr(args, "verify", False)),
                home_dir=args.home_dir,
                stdin=sys.stdin,
                stdout=sys.stdout,
            )
        except (argparse.ArgumentTypeError, ValueError) as exc:
            return _emit_footer_failure(
                command=args.command,
                footer=args.footer,
                home_dir=args.home_dir,
                error=exc,
            )

    if args.command == "install" and (args.apply or args.verify):
        try:
            report, exit_code = run_install(
                instance_name=args.instance,
                root_dir=args.root_dir,
                apply=args.apply,
                verify=args.verify,
                home_dir=args.home_dir,
                version=args.version,
                artifact=args.artifact,
                artifact_sha256=args.artifact_sha256,
            )
        except ArtifactVerificationError as exc:
            payload = {"command": "install", "status": "failed", "error": str(exc)}
            if footer_detected is not None and footer_selection is not None:
                _attach_footer_metadata(
                    payload,
                    detected_agents=footer_detected,
                    footer_selection=footer_selection,
                )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
        if exit_code == 0 and args.apply and selected_footer is not None:
            try:
                footer_selection["config_write"] = write_footer_config(
                    selected_footer,
                    home_dir=args.home_dir,
                )
            except Exception as exc:
                report["status"] = "failed"
                report["error"] = str(exc)
                footer_selection["config_write"] = {
                    "status": "failed",
                    "error": str(exc),
                }
                exit_code = 1
        if footer_detected is not None and footer_selection is not None:
            _attach_footer_metadata(
                report,
                detected_agents=footer_detected,
                footer_selection=footer_selection,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    if args.command == "upgrade" and (args.apply or args.verify):
        try:
            report, exit_code = run_upgrade(
                instance_name=args.instance,
                root_dir=args.root_dir,
                apply=args.apply,
                verify=args.verify,
                home_dir=args.home_dir,
                version=args.version,
                artifact=args.artifact,
                artifact_sha256=args.artifact_sha256,
            )
        except ArtifactVerificationError as exc:
            payload = {"command": "upgrade", "status": "failed", "error": str(exc)}
            if footer_detected is not None and footer_selection is not None:
                _attach_footer_metadata(
                    payload,
                    detected_agents=footer_detected,
                    footer_selection=footer_selection,
                )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
        if exit_code == 0 and args.apply and selected_footer is not None:
            try:
                footer_selection["config_write"] = write_footer_config(
                    selected_footer,
                    home_dir=args.home_dir,
                )
            except Exception as exc:
                report["status"] = "failed"
                report["error"] = str(exc)
                footer_selection["config_write"] = {
                    "status": "failed",
                    "error": str(exc),
                }
                exit_code = 1
        if footer_detected is not None and footer_selection is not None:
            _attach_footer_metadata(
                report,
                detected_agents=footer_detected,
                footer_selection=footer_selection,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    if args.command == "uninstall" and args.apply:
        report, exit_code = run_uninstall(
            instance_name=args.instance,
            root_dir=args.root_dir,
            apply=args.apply,
            home_dir=args.home_dir,
            purge_state=args.purge_state,
            purge_secret=args.purge_secret,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    if args.command == "status":
        record = read_install_record(home_dir=args.home_dir, instance_name=args.instance)
        print(json.dumps(record, ensure_ascii=False, indent=2) if record else "{}")
        return 0

    if args.command == "rollback":
        report, exit_code = run_rollback(
            instance_name=args.instance,
            root_dir=args.root_dir,
            home_dir=args.home_dir,
            command=args.from_command,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    plan = build_command_plan(
        args.command,
        instance_name=args.instance,
        root_dir=args.root_dir,
    )
    if args.command in ("install", "upgrade"):
        try:
            prepared = preflight_templates(plan)
        except TemplatePreflightError as exc:
            report, exit_code = _record_template_preflight_failure(
                {
                    "command": args.command,
                    "instance_name": args.instance,
                    "root_dir": args.root_dir,
                    "status": "failed",
                },
                exc,
            )
            if footer_detected is None or footer_selection is None:
                footer_detected = detect_agents(home=_resolve_footer_home(args.home_dir))
                footer_selection = {"mode": "skipped", "reason": "plan-only"}
            _attach_footer_metadata(
                report,
                detected_agents=footer_detected,
                footer_selection=footer_selection,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return exit_code
        plan_payload = plan.as_dict()
        plan_payload["template_preflight"] = {
            "status": "passed",
            "checked_assets": sorted(prepared),
        }
        if footer_detected is None or footer_selection is None:
            footer_detected = detect_agents(home=_resolve_footer_home(args.home_dir))
            footer_selection = {"mode": "skipped", "reason": "plan-only"}
        _attach_footer_metadata(
            plan_payload,
            detected_agents=footer_detected,
            footer_selection=footer_selection,
        )
        print(json.dumps(plan_payload, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
