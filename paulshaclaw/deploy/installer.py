from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from paulshaclaw.config import paths
from paulshaclaw.core.config import load_config

from .planner import CommandPlan, TemplateAsset, build_command_plan


class DeploymentVerificationError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def render_template(asset: TemplateAsset, *, instance_name: str, root_dir: str) -> str:
    return (
        asset.template_path.read_text(encoding="utf-8")
        .replace("__INSTANCE__", instance_name)
        .replace("__ROOT_DIR__", root_dir)
    )


def resolve_install_path(asset: TemplateAsset, *, home_dir: Path) -> Path:
    target = Path(asset.target_path)
    if target.parts[:2] == ("core", "systemd"):
        return home_dir / ".config" / "systemd" / "user" / target.name
    if target.parts[:2] == ("core", "runtime"):
        return home_dir / ".agents" / "core" / "runtime" / target.name
    if target.parts[:2] == ("state", "config"):
        return home_dir / ".agents" / "state" / "config" / target.name
    if target.parts[:2] == ("secret", "bootstrap"):
        return home_dir / ".config" / "paulshaclaw" / target.name
    raise ValueError(f"unsupported template target: {asset.target_path}")


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _user_systemd_available() -> bool:
    if shutil.which("systemctl") is None:
        return False
    completed = _run_command(["systemctl", "--user", "show-environment"])
    return completed.returncode == 0


def _run_daemon_reload() -> str:
    if not _user_systemd_available():
        return "skipped"
    completed = _run_command(["systemctl", "--user", "daemon-reload"])
    if completed.returncode == 0:
        return "ran"
    return "skipped"


def _ensure_linger_enabled() -> str:
    if shutil.which("loginctl") is None:
        return "unavailable"

    user_name = (
        os.environ.get("LOGNAME")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or ""
    )
    if not user_name:
        return "unavailable"

    status = _run_command(["loginctl", "show-user", user_name, "-p", "Linger", "--value"])
    if status.returncode == 0 and status.stdout.strip() == "yes":
        return "already-enabled"

    enabled = _run_command(["loginctl", "enable-linger", user_name])
    if enabled.returncode == 0:
        return "enabled"
    return "unavailable"


def _parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, _value = stripped.partition("=")
        if separator:
            keys.add(key.strip())
    return keys


def _apply_permissions(asset: TemplateAsset, destination: Path) -> None:
    if asset.plane == "secret":
        destination.parent.chmod(0o700)
        destination.chmod(0o600)
    elif asset.plane == "state":
        destination.parent.chmod(0o750)
        destination.chmod(0o640)


def _verify_env_catalog(plan: CommandPlan, *, home_dir: Path) -> list[str]:
    errors: list[str] = []
    for asset in plan.templates:
        path = resolve_install_path(asset, home_dir=home_dir)
        if asset.plane == "state" and asset.target_path.endswith(".state.json"):
            if not path.is_file():
                errors.append(f"missing required state file: {path.name} ({path})")
                continue
            try:
                load_config(config_path=path)
            except Exception as exc:
                errors.append(f"invalid state config {path.name}: {exc}")
            continue
        if not asset.required_keys:
            continue
        if not path.is_file():
            errors.append(f"missing required env file: {path.name} ({path})")
            continue
        existing_keys = _parse_env_keys(path)
        missing_keys = [key for key in asset.required_keys if key not in existing_keys]
        if missing_keys:
            errors.append(f"missing required env keys in {path.name}: {', '.join(missing_keys)}")
    return errors


def _verify_systemd_units(plan: CommandPlan, *, home_dir: Path) -> dict[str, object]:
    unit_dir = home_dir / ".config" / "systemd" / "user"
    missing_units = [str(unit_dir / unit_name) for unit_name in plan.verify_units if not (unit_dir / unit_name).is_file()]
    if missing_units:
        return {"status": "failed", "issues": [f"missing required unit file: {path}" for path in missing_units]}

    if shutil.which("systemd-analyze") is None or not _user_systemd_available():
        return {"status": "on-host-only"}

    unit_paths = [str(unit_dir / unit_name) for unit_name in plan.verify_units]

    completed = _run_command(["systemd-analyze", "--user", "verify", *unit_paths])
    if completed.returncode == 0:
        return {"status": "passed", "checked_units": list(plan.verify_units)}

    stderr = completed.stderr.lower()
    if "failed to connect to user bus" in stderr or "failed to connect to bus" in stderr:
        return {"status": "on-host-only"}
    return {
        "status": "failed",
        "issues": ["systemd-analyze --user verify failed", completed.stderr.strip() or completed.stdout.strip()],
    }


def _asset_is_overwritable(asset: TemplateAsset) -> bool:
    """僅 unit 檔（core/systemd/**）允許覆寫（模板演進屬部署面職責）。

    core/runtime env 值檔、state、secret 為使用者持有：rerun 覆寫會以
    placeholder 毀掉真實設定（#219 對抗審查 F1；硬規範「不可破壞」），
    故一律 create-only——存在即跳過，強制重建走明確刪檔或 uninstall。
    """
    return asset.template_relpath.startswith("core/systemd/")


def apply_install_plan(plan: CommandPlan, *, home_dir: Path) -> dict[str, list[str]]:
    written_files: list[str] = []
    skipped_existing: list[str] = []
    for asset in plan.templates:
        destination = resolve_install_path(asset, home_dir=home_dir)
        if destination.exists() and not _asset_is_overwritable(asset):
            skipped_existing.append(str(destination))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            render_template(asset, instance_name=plan.instance_name, root_dir=plan.root_dir),
            encoding="utf-8",
        )
        _apply_permissions(asset, destination)
        written_files.append(str(destination))
    return {"written": sorted(written_files), "skipped_existing": sorted(skipped_existing)}


def verify_install_plan(plan: CommandPlan, *, home_dir: Path) -> dict[str, object]:
    env_errors = _verify_env_catalog(plan, home_dir=home_dir)
    systemd_result = _verify_systemd_units(plan, home_dir=home_dir)
    issues = list(env_errors)
    if systemd_result.get("status") == "failed":
        issues.extend(issue for issue in systemd_result.get("issues", ()) if issue)
    return {
        "status": "failed" if issues else "passed",
        "issues": issues,
        "systemd": systemd_result,
    }


def run_install(*, instance_name: str, root_dir: str, apply: bool, verify: bool, home_dir: str | Path | None = None) -> tuple[dict[str, object], int]:
    plan = build_command_plan("install", instance_name=instance_name, root_dir=root_dir)
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else paths.home_root()
    report: dict[str, object] = {
        "command": "install",
        "instance_name": instance_name,
        "root_dir": root_dir,
        "status": "ok",
    }

    if apply:
        applied = apply_install_plan(plan, home_dir=resolved_home)
        report["applied_files"] = applied["written"]
        report["skipped_existing"] = applied["skipped_existing"]
        report["linger"] = _ensure_linger_enabled()
        report["daemon_reload"] = _run_daemon_reload()

    if verify:
        verification = verify_install_plan(plan, home_dir=resolved_home)
        report["verification"] = verification
        if verification["status"] != "passed":
            report["status"] = "failed"
            return report, 1

    return report, 0
