from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = PACKAGE_ROOT / "templates"


@dataclass(frozen=True)
class TemplateAsset:
    plane: str
    template_relpath: str
    target_path: str
    rename_rule: str
    expected_suffix: str

    @property
    def template_path(self) -> Path:
        return TEMPLATE_ROOT / self.template_relpath

    def as_dict(self) -> dict[str, object]:
        return {
            "plane": self.plane,
            "template_path": str(self.template_path),
            "target_path": self.target_path,
            "rename_rule": self.rename_rule,
            "expected_suffix": self.expected_suffix,
        }


@dataclass(frozen=True)
class PermissionCheck:
    plane: str
    mode: int
    allowed: bool
    reason: str


@dataclass(frozen=True)
class SecretInstallStep:
    step_id: str
    prompt: str
    required: bool = True


@dataclass(frozen=True)
class CommandPlan:
    command: str
    instance_name: str
    root_dir: str
    templates: tuple[TemplateAsset, ...]
    steps: tuple[str, ...]
    rollback_checkpoints: tuple[str, ...]
    rollback_actions: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "instance_name": self.instance_name,
            "root_dir": self.root_dir,
            "templates": [asset.as_dict() for asset in self.templates],
            "steps": list(self.steps),
            "rollback_checkpoints": list(self.rollback_checkpoints),
            "rollback_actions": list(self.rollback_actions),
        }


_TEMPLATE_CATALOG: tuple[tuple[str, str, str], ...] = (
    (
        "core",
        "core/systemd/__INSTANCE__.service.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "core",
        "core/runtime/__INSTANCE__.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "state",
        "state/config/__INSTANCE__.state.json.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "secret",
        "secret/bootstrap/__INSTANCE__.secret.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
)

_SECRET_INSTALL_STEPS: tuple[SecretInstallStep, ...] = (
    SecretInstallStep("secret_source", "輸入 secret 來源（私有 repo 或離線封裝路徑）"),
    SecretInstallStep("secret_target", "確認 secret plane 目標目錄"),
    SecretInstallStep("permission_ack", "確認 secret plane 將以 0700/0600 權限建立，請輸入 yes"),
)

_COMMAND_MATRIX: dict[str, dict[str, tuple[str, ...]]] = {
    "install": {
        "steps": (
            "render-core-templates",
            "initialize-state-plane",
            "interactive-secret-install",
            "enable-service-unit",
        ),
        "rollback_checkpoints": (
            "pre-install",
            "post-core-render",
            "post-state-init",
            "post-secret-install",
        ),
        "rollback_actions": (
            "restore-core-from-checkpoint",
            "remove-new-state-if-created",
            "restore-secret-from-checkpoint",
        ),
    },
    "upgrade": {
        "steps": (
            "snapshot-existing-core",
            "render-core-templates",
            "preserve-state-plane",
            "preserve-secret-plane",
            "restart-service-unit",
        ),
        "rollback_checkpoints": (
            "pre-upgrade",
            "post-core-render",
        ),
        "rollback_actions": (
            "restore-core-from-checkpoint",
            "preserve-state",
            "preserve-secret",
        ),
    },
    "uninstall": {
        "steps": (
            "snapshot-existing-core",
            "disable-service-unit",
            "remove-core-plane",
            "preserve-state-plane",
            "preserve-secret-plane",
        ),
        "rollback_checkpoints": (
            "pre-uninstall",
            "post-service-disable",
        ),
        "rollback_actions": (
            "restore-core-from-checkpoint",
            "preserve-state",
            "preserve-secret",
        ),
    },
}


def resolve_template_target(template_relpath: str, *, instance_name: str) -> str:
    target = template_relpath.replace("__INSTANCE__", instance_name)
    if target.endswith(".tmpl"):
        target = target[: -len(".tmpl")]
    return target


def _expected_suffix(target_path: str) -> str:
    parts = Path(target_path).name.split(".")
    if len(parts) <= 1:
        return Path(target_path).name
    return "." + ".".join(parts[1:])


def list_template_assets(*, instance_name: str = "paulshaclaw") -> tuple[TemplateAsset, ...]:
    assets: list[TemplateAsset] = []
    for plane, template_relpath, rename_rule in _TEMPLATE_CATALOG:
        target_path = resolve_template_target(template_relpath, instance_name=instance_name)
        assets.append(
            TemplateAsset(
                plane=plane,
                template_relpath=template_relpath,
                target_path=target_path,
                rename_rule=rename_rule,
                expected_suffix=_expected_suffix(target_path),
            )
        )
    return tuple(assets)


def validate_plane_permissions(plane: str, mode: int) -> PermissionCheck:
    normalized_mode = mode & 0o777
    if plane == "state":
        forbidden_mask = 0o027
        if normalized_mode & forbidden_mask:
            return PermissionCheck(
                plane=plane,
                mode=normalized_mode,
                allowed=False,
                reason="state plane 不可為 group writable 或任何 other 權限",
            )
    elif plane == "secret":
        forbidden_mask = 0o077
        if normalized_mode & forbidden_mask:
            return PermissionCheck(
                plane=plane,
                mode=normalized_mode,
                allowed=False,
                reason="secret plane 僅允許 owner 權限，需符合 0700/0600",
            )
    elif plane != "core":
        raise ValueError(f"未知 plane: {plane}")

    return PermissionCheck(
        plane=plane,
        mode=normalized_mode,
        allowed=True,
        reason=f"{plane} plane 權限符合基線",
    )


def build_secret_install_steps() -> tuple[SecretInstallStep, ...]:
    return _SECRET_INSTALL_STEPS


def complete_secret_install_flow(answers: dict[str, str]) -> dict[str, object]:
    missing = [step.step_id for step in _SECRET_INSTALL_STEPS if step.required and not answers.get(step.step_id)]
    if missing:
        raise ValueError(f"secret install 缺少欄位: {', '.join(missing)}")

    permission_ack = answers["permission_ack"].strip().lower()
    if permission_ack != "yes":
        raise ValueError("secret plane 需要確認 0700/0600 權限後才能安裝")

    permission_check = validate_plane_permissions("secret", 0o700)
    if not permission_check.allowed:
        raise ValueError(permission_check.reason)

    secret_source = answers["secret_source"].strip()
    source_kind = "private-repo" if "://" in secret_source or secret_source.startswith("git@") else "offline-bundle"
    return {
        "plane": "secret",
        "source": secret_source,
        "source_kind": source_kind,
        "target": answers["secret_target"].strip(),
        "steps": [step.prompt for step in _SECRET_INSTALL_STEPS],
        "checkpoints": ["secret-preflight", "secret-installed"],
        "permission_reason": permission_check.reason,
    }


def build_command_plan(command: str, *, instance_name: str, root_dir: str) -> CommandPlan:
    if command not in _COMMAND_MATRIX:
        raise ValueError(f"不支援的 command: {command}")

    matrix = _COMMAND_MATRIX[command]
    return CommandPlan(
        command=command,
        instance_name=instance_name,
        root_dir=root_dir,
        templates=list_template_assets(instance_name=instance_name),
        steps=matrix["steps"],
        rollback_checkpoints=matrix["rollback_checkpoints"],
        rollback_actions=matrix["rollback_actions"],
    )
