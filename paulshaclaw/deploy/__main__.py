from __future__ import annotations

import argparse
import json
import shutil
import sys
from typing import Any, Sequence

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
_FOOTER_PROVIDERS = ("copilot", "claude", "codex", "agy")


def _isatty(stream: object) -> bool:
    try:
        isatty = getattr(stream, "isatty")
    except Exception:
        return False
    try:
        return bool(isatty())
    except Exception:
        return False


def _parse_footer_argument(raw: str) -> dict[str, object]:
    value = raw.strip()
    if not value:
        raise argparse.ArgumentTypeError("--footer 不可為空")
    if value == "none":
        return {"raw": value, "provider": "none", "labels": []}

    parts = value.split(":")
    if any(not part for part in parts):
        raise argparse.ArgumentTypeError("--footer 格式錯誤")

    provider, *labels = parts
    if provider not in _FOOTER_PROVIDERS:
        allowed = ", ".join((*_FOOTER_PROVIDERS, "none"))
        raise argparse.ArgumentTypeError(f"--footer 僅支援 {allowed}")
    if provider == "copilot":
        if not labels:
            raise argparse.ArgumentTypeError("copilot footer 需至少一個 account label")
    elif labels:
        raise argparse.ArgumentTypeError(f"{provider} footer 不接受額外 label")

    return {"raw": value, "provider": provider, "labels": labels}


def _detect_agents() -> dict[str, dict[str, object]]:
    detected: dict[str, dict[str, object]] = {}
    for provider in _FOOTER_PROVIDERS:
        cli_path = shutil.which(provider)
        detected[provider] = {
            "detected": cli_path is not None,
            "cli_path": cli_path,
        }
    return detected


def _footer_metadata(
    command: str,
    *,
    footer: dict[str, object] | None,
    plan_only: bool,
) -> dict[str, Any]:
    if footer is not None:
        selection: dict[str, Any] = {
            "mode": "flag",
            "requested": footer["raw"],
            "provider": footer["provider"],
        }
        labels = list(footer.get("labels", []))
        if labels:
            selection["labels"] = labels
    elif plan_only:
        selection = {"mode": "skipped", "reason": "plan-only"}
    elif not (_isatty(sys.stdin) and _isatty(sys.stdout)):
        selection = {"mode": "skipped", "reason": "no-tty"}
    else:
        selection = {"mode": "skipped", "reason": "interactive-selection-pending"}

    return {
        "command": command,
        "detected_agents": _detect_agents(),
        "footer_selection": selection,
    }


def _attach_footer_metadata(
    payload: dict[str, object],
    command: str,
    *,
    footer: dict[str, object] | None,
    plan_only: bool,
) -> dict[str, object]:
    if command not in ("install", "upgrade"):
        return payload
    payload.update(_footer_metadata(command, footer=footer, plan_only=plan_only))
    return payload


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
                type=_parse_footer_argument,
                default=None,
                help="footer agent/account 選擇；支援 none 與 copilot:<label>[:label...]",
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
            payload = _attach_footer_metadata(
                {"command": "install", "status": "failed", "error": str(exc)},
                "install",
                footer=args.footer,
                plan_only=False,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
        _attach_footer_metadata(report, "install", footer=args.footer, plan_only=False)
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
            payload = _attach_footer_metadata(
                {"command": "upgrade", "status": "failed", "error": str(exc)},
                "upgrade",
                footer=args.footer,
                plan_only=False,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
        _attach_footer_metadata(report, "upgrade", footer=args.footer, plan_only=False)
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
            _attach_footer_metadata(report, args.command, footer=args.footer, plan_only=True)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return exit_code
        plan_payload = plan.as_dict()
        plan_payload["template_preflight"] = {
            "status": "passed",
            "checked_assets": sorted(prepared),
        }
        _attach_footer_metadata(plan_payload, args.command, footer=args.footer, plan_only=True)
        print(json.dumps(plan_payload, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
