from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = PACKAGE_ROOT / "templates"


@dataclass(frozen=True)
class TemplateAsset:
    plane: str
    template_relpath: str
    target_path: str
    rename_rule: str
    expected_suffix: str
    deploy: bool = True
    deprecated: bool = False
    env_catalog: tuple[str, ...] = ()
    required_keys: tuple[str, ...] = ()

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
            "deploy": self.deploy,
            "deprecated": self.deprecated,
            "env_catalog": list(self.env_catalog),
            "required_keys": list(self.required_keys),
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
    verify_units: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "instance_name": self.instance_name,
            "root_dir": self.root_dir,
            "templates": [asset.as_dict() for asset in self.templates],
            "steps": list(self.steps),
            "rollback_checkpoints": list(self.rollback_checkpoints),
            "rollback_actions": list(self.rollback_actions),
            "verify_units": list(self.verify_units),
        }


@dataclass(frozen=True)
class _TemplateSpec:
    plane: str
    template_relpath: str
    rename_rule: str
    deploy: bool = True
    deprecated: bool = False
    env_catalog: tuple[str, ...] = ()
    required_keys: tuple[str, ...] = ()


_TEMPLATE_CATALOG: tuple[_TemplateSpec, ...] = (
    _TemplateSpec(
        plane="core",
        template_relpath="core/systemd/__INSTANCE__.service.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        # not-deployed（#219 對抗審查 F3）：ExecStart 跑 core.daemon（command CLI，
        # 非常駐入口）必於參數解析失敗；core 服務化另案，先排除於 install/verify。
        deploy=False,
        deprecated=True,
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/systemd/__INSTANCE__-dream.service.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        env_catalog=("core/runtime/__INSTANCE__.env", "core/runtime/__INSTANCE__-dream.env"),
        # #125 Phase 1 已執行：dream 常駐移交 paulsha-hippo installer
        # （hippo install service）；本模板退出部署面（adr-001 拆分注記）。
        deploy=False,
        deprecated=True,
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/systemd/__INSTANCE__-cost.service.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        env_catalog=("core/runtime/__INSTANCE__.env", "core/runtime/__INSTANCE__-cost.env"),
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/systemd/__INSTANCE__-telegram.service.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        env_catalog=(
            "core/runtime/__INSTANCE__.env",
            "core/runtime/__INSTANCE__-telegram.env",
            "secret/bootstrap/__INSTANCE__.telegram.secret.env",
        ),
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/runtime/__INSTANCE__.env.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        required_keys=("PSC_INSTANCE", "PSC_PLANE"),
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/runtime/__INSTANCE__-dream.env.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        required_keys=("PSC_MEMORY_ROOT", "PSC_DREAM_INTERVAL_SECONDS", "PSC_EXTRA_CORPUS_ROOT"),
        # #125：dream 常駐（unit+env）移交 paulsha-hippo installer。
        deploy=False,
        deprecated=True,
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/runtime/__INSTANCE__-cost.env.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        required_keys=("PAULSHACLAW_CONFIG",),
    ),
    _TemplateSpec(
        plane="core",
        template_relpath="core/runtime/__INSTANCE__-telegram.env.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        required_keys=("PSC_INSTANCE", "PSC_PLANE"),
    ),
    _TemplateSpec(
        plane="state",
        template_relpath="state/config/__INSTANCE__.state.json.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    _TemplateSpec(
        plane="secret",
        template_relpath="secret/bootstrap/__INSTANCE__.secret.env.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        required_keys=("PSC_INSTANCE", "PSC_SECRET_BOOTSTRAP"),
    ),
    _TemplateSpec(
        plane="secret",
        template_relpath="secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl",
        rename_rule="以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
        required_keys=(
            "PSC_TELEGRAM_BOT_TOKEN",
            "PSC_TELEGRAM_EXPECTED_USERNAME",
            "PSC_TELEGRAM_EXPECTED_BOT_ID",
            "PSC_CLAUDE_GEMMA4_API_KEY",
        ),
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
            "daemon-reload-user-units",
            "verify-required-env-catalog",
            "verify-systemd-user-units",
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
            "verify-systemd-user-units",
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


def list_template_assets(*, instance_name: str = "paulshaclaw", deployed_only: bool = False) -> tuple[TemplateAsset, ...]:
    assets: list[TemplateAsset] = []
    for spec in _TEMPLATE_CATALOG:
        if deployed_only and not spec.deploy:
            continue
        target_path = resolve_template_target(spec.template_relpath, instance_name=instance_name)
        assets.append(
            TemplateAsset(
                plane=spec.plane,
                template_relpath=spec.template_relpath,
                target_path=target_path,
                rename_rule=spec.rename_rule,
                expected_suffix=_expected_suffix(target_path),
                deploy=spec.deploy,
                deprecated=spec.deprecated,
                env_catalog=spec.env_catalog,
                required_keys=spec.required_keys,
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

    templates = list_template_assets(instance_name=instance_name, deployed_only=True)
    verify_units = tuple(
        Path(asset.target_path).name
        for asset in templates
        if asset.template_relpath.startswith("core/systemd/") and asset.target_path.endswith(".service")
    )
    matrix = _COMMAND_MATRIX[command]
    return CommandPlan(
        command=command,
        instance_name=instance_name,
        root_dir=root_dir,
        templates=templates,
        steps=matrix["steps"],
        rollback_checkpoints=matrix["rollback_checkpoints"],
        rollback_actions=matrix["rollback_actions"],
        verify_units=verify_units,
    )
