from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .planner import TemplateAsset, build_command_plan


class DeploymentVerificationError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class InstallResult:
    written_files: tuple[str, ...]
    linger_status: str
    daemon_reload: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "written_files": list(self.written_files),
            "linger_status": self.linger_status,
            "daemon_reload": self.daemon_reload,
        }


@dataclass(frozen=True)
class VerifyResult:
    checked_files: tuple[str, ...]
    systemd_verify: str

    def as_dict(self) -> dict[str, object]:
        return {
            "checked_files": list(self.checked_files),
            "systemd_verify": self.systemd_verify,
        }


_REQUIRED_ENV_KEYS: dict[str, tuple[str, ...]] = {
    ".agents/core/runtime/{instance}.env": ("PSC_INSTANCE", "PSC_SECRET_BOOTSTRAP"),
    ".agents/core/runtime/{instance}-telegram.env": ("PSC_INSTANCE", "PSC_PLANE"),
    ".config/paulshaclaw/{instance}.telegram.secret.env": (
        "PSC_TELEGRAM_BOT_TOKEN",
        "PSC_TELEGRAM_EXPECTED_USERNAME",
        "PSC_TELEGRAM_EXPECTED_BOT_ID",
        "PSC_CLAUDE_GEMMA4_API_KEY",
    ),
    ".agents/core/runtime/{instance}-manager.env": (
        "PSC_INSTANCE",
        "PSC_PLANE",
        "PSC_CONTROL_ROOT",
        "PSC_MANAGER_EXECUTOR",
        "PSC_MANAGER_INTERVAL_SECONDS",
    ),
    ".agents/core/runtime/{instance}-dream.env": (
        "PSC_INSTANCE",
        "PSC_PLANE",
        "PSC_MEMORY_ROOT",
        "PSC_DREAM_INTERVAL_SECONDS",
        "PSC_DREAM_INSTRUCTION_ROOTS",
    ),
    ".agents/core/runtime/{instance}-cost.env": (
        "PSC_INSTANCE",
        "PSC_PLANE",
        "PAULSHACLAW_CONFIG",
        "PSC_COST_REFRESH_INTERVAL_SECONDS",
    ),
}


def _destination_path(asset: TemplateAsset, *, home_dir: Path) -> Path:
    relpath = Path(asset.target_path)
    if relpath.parts[:2] == ("core", "systemd"):
        return home_dir / ".config" / "systemd" / "user" / relpath.name
    if relpath.parts[:2] == ("core", "runtime"):
        return home_dir / ".agents" / "core" / "runtime" / relpath.name
    if relpath.parts[:2] == ("state", "config"):
        return home_dir / ".agents" / "state" / "config" / relpath.name
    if relpath.parts[:2] == ("secret", "bootstrap"):
        return home_dir / ".config" / "paulshaclaw" / relpath.name
    raise ValueError(f"unsupported template target: {asset.target_path}")


def _render_template(asset: TemplateAsset, *, instance_name: str, root_dir: str) -> str:
    return (
        asset.template_path.read_text(encoding="utf-8")
        .replace("__INSTANCE__", instance_name)
        .replace("__ROOT_DIR__", root_dir)
    )


def _daemon_reload() -> bool:
    if shutil.which("systemctl") is None:
        return False
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=True,
        capture_output=True,
        text=True,
    )
    return True


def _ensure_linger(*, user: str) -> str:
    if shutil.which("loginctl") is None:
        return "unavailable"
    status = subprocess.run(
        ["loginctl", "show-user", user, "-p", "Linger", "--value"],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode == 0 and status.stdout.strip() == "yes":
        return "already-enabled"
    subprocess.run(
        ["loginctl", "enable-linger", user],
        check=True,
        capture_output=True,
        text=True,
    )
    return "enabled"


def install_deployment(
    *,
    instance_name: str,
    root_dir: str,
    home_dir: str | Path | None = None,
    user: str | None = None,
) -> InstallResult:
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else Path.home()
    plan = build_command_plan("install", instance_name=instance_name, root_dir=root_dir)
    written_files: list[str] = []
    for asset in plan.templates:
        destination = _destination_path(asset, home_dir=resolved_home)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            _render_template(asset, instance_name=instance_name, root_dir=root_dir),
            encoding="utf-8",
        )
        written_files.append(str(destination))
    daemon_reload = _daemon_reload()
    linger_status = _ensure_linger(user=user or os.environ.get("USER", ""))
    return InstallResult(
        written_files=tuple(sorted(written_files)),
        linger_status=linger_status,
        daemon_reload=daemon_reload,
    )


def _env_file_path(home_dir: Path, pattern: str, instance_name: str) -> Path:
    return home_dir / pattern.format(instance=instance_name)


def _parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, _value = stripped.partition("=")
        if sep:
            keys.add(key.strip())
    return keys


def _systemd_verify_status(*, home_dir: Path, instance_name: str) -> str:
    if shutil.which("systemd-analyze") is None:
        return "on-host-only"
    unit_dir = home_dir / ".config" / "systemd" / "user"
    unit_paths = sorted(str(path) for path in unit_dir.glob(f"{instance_name}*.service"))
    if not unit_paths:
        return "on-host-only"
    completed = subprocess.run(
        ["systemd-analyze", "--user", "verify", *unit_paths],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return "ok"
    stderr = completed.stderr.lower()
    if completed.returncode == 127 or "unavailable" in stderr or "failed to connect to bus" in stderr:
        return "on-host-only"
    raise DeploymentVerificationError(["systemd-analyze --user verify failed"])


def verify_deployment(
    *,
    instance_name: str,
    home_dir: str | Path | None = None,
) -> VerifyResult:
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else Path.home()
    checked_files: list[str] = []
    errors: list[str] = []
    for pattern, required_keys in _REQUIRED_ENV_KEYS.items():
        path = _env_file_path(resolved_home, pattern, instance_name)
        checked_files.append(str(path))
        if not path.is_file():
            errors.append(f"missing required env file: {path}")
            continue
        keys = _parse_env_keys(path)
        missing_keys = [key for key in required_keys if key not in keys]
        if missing_keys:
            errors.append(f"missing required env keys in {path}: {', '.join(missing_keys)}")
    if errors:
        raise DeploymentVerificationError(errors)
    return VerifyResult(
        checked_files=tuple(sorted(checked_files)),
        systemd_verify=_systemd_verify_status(home_dir=resolved_home, instance_name=instance_name),
    )
