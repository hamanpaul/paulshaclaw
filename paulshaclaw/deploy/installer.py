from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
except Exception:  # pragma: no cover - 純防護
    _pkg_version = None

from paulshaclaw.config import paths
from paulshaclaw.core.config import load_config

from .planner import CommandPlan, TemplateAsset, build_command_plan


class DeploymentVerificationError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


class ArtifactVerificationError(RuntimeError):
    """artifact 來源驗證失敗（checksum 不符或檔案不存在），必須 fail-closed。"""


def detect_installed_version() -> str | None:
    """偵測目前安裝的 paulshaclaw 版本；不可得時回 None。"""
    if _pkg_version is not None:
        try:
            return _pkg_version("paulshaclaw")
        except Exception:
            pass
    version_file = paths.repo_root() / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


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


def run_install(*, instance_name: str, root_dir: str, apply: bool, verify: bool, home_dir: str | Path | None = None, version: str | None = None, artifact: str | None = None, artifact_sha256: str | None = None) -> tuple[dict[str, object], int]:
    plan = build_command_plan("install", instance_name=instance_name, root_dir=root_dir)
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else paths.home_root()
    report: dict[str, object] = {
        "command": "install",
        "instance_name": instance_name,
        "root_dir": root_dir,
        "status": "ok",
    }

    if apply:
        # E1：artifact 來源驗證（fail-closed）。
        artifact_record = _verify_and_record_artifact(
            artifact=artifact,
            artifact_sha256=artifact_sha256,
        )
        report["artifact"] = artifact_record
        applied = apply_install_plan(plan, home_dir=resolved_home)
        report["applied_files"] = applied["written"]
        report["skipped_existing"] = applied["skipped_existing"]
        report["linger"] = _ensure_linger_enabled()
        report["daemon_reload"] = _run_daemon_reload()
        _write_install_record(
            resolved_home,
            instance_name=instance_name,
            command="install",
            version=version,
            artifact=artifact,
            artifact_sha256=artifact_record["sha256"],
        )

    if verify:
        verification = verify_install_plan(plan, home_dir=resolved_home)
        report["verification"] = verification
        if verification["status"] != "passed":
            report["status"] = "failed"
            return report, 1

    return report, 0


# ---------------------------------------------------------------------------
# E1：安裝來源記錄與查詢入口
# ---------------------------------------------------------------------------

INSTALL_RECORD_FILENAME = "{instance}.install-record.json"


def _install_record_path(home_dir: Path, *, instance_name: str) -> Path:
    return home_dir / ".agents" / "state" / "config" / INSTALL_RECORD_FILENAME.format(instance=instance_name)


def _verify_and_record_artifact(*, artifact: str | None, artifact_sha256: str | None) -> dict[str, object]:
    """驗證 artifact 來源並回傳可記錄的摘要。

    fail-closed：指定本地 artifact 但檔案不存在、或指定 sha256 但不符，皆拋
    `ArtifactVerificationError`；只給 `--artifact-sha256` 而沒給 `--artifact`
    同樣 fail-closed——沒有 artifact 可算，記下來的 checksum 會讓 operator
    誤以為驗證過。

    `verified` 欄位誠實標示這個 sha256 是否真的算過：只有本地檔案實算才是
    `True`。URL artifact 不下載驗證（不在本階段範圍），僅記錄來源字串與
    operator 提供的 checksum。
    """
    record: dict[str, object] = {"source": artifact, "sha256": artifact_sha256, "verified": False}
    if artifact is None:
        if artifact_sha256 is not None:
            raise ArtifactVerificationError(
                "指定 --artifact-sha256 時必須同時指定 --artifact，否則沒有任何 artifact 可驗證"
            )
        return record
    # URL 來源：本階段不下載驗證，只記錄。
    if "://" in artifact:
        return record
    artifact_path = Path(artifact).expanduser()
    if not artifact_path.is_file():
        raise ArtifactVerificationError(f"artifact 檔案不存在：{artifact}")
    computed = _sha256(artifact_path)
    record["sha256"] = computed
    if artifact_sha256 is not None and computed.lower() != artifact_sha256.lower():
        raise ArtifactVerificationError(
            f"artifact SHA-256 不符：期望 {artifact_sha256}，實際 {computed}"
        )
    record["verified"] = True
    return record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_install_record(
    home_dir: Path,
    *,
    instance_name: str,
    command: str,
    version: str | None,
    artifact: str | None,
    artifact_sha256: str | None,
) -> Path:
    record_path = _install_record_path(home_dir, instance_name=instance_name)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instance": instance_name,
        "command": command,
        "version": version or detect_installed_version(),
        "artifact_source": artifact,
        "artifact_sha256": artifact_sha256,
        "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        record_path.chmod(0o640)
    except OSError:
        pass
    return record_path


def read_install_record(home_dir: str | Path | None = None, *, instance_name: str = "paulshaclaw") -> dict[str, object] | None:
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else paths.home_root()
    record_path = _install_record_path(resolved_home, instance_name=instance_name)
    if not record_path.is_file():
        return None
    return json.loads(record_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# E3/E4：core plane snapshot 與 restore（rollback checkpoint）
# ---------------------------------------------------------------------------

CHECKPOINT_RELPATH = ".agents/deploy-checkpoints"


def _checkpoint_root(home_dir: Path, *, instance_name: str) -> Path:
    return home_dir / CHECKPOINT_RELPATH / instance_name


def _new_checkpoint_dir(home_dir: Path, *, instance_name: str, command: str) -> Path:
    """建立一個必定唯一的 checkpoint 目錄。

    秒級 timestamp + `exist_ok=True` 會讓同一秒內的兩次 upgrade 共用同一個
    目錄：後者的 snapshot 覆寫前者，而 `latest_checkpoint()` 依名稱排序仍只看到
    一個——rollback 會還原到「已經被改過」的內容而非升級前。故改用微秒精度，
    並以 `exist_ok=False` + 遞增序號確保每次都是新目錄。
    """
    base = _checkpoint_root(home_dir, instance_name=instance_name)
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S.%f")
    candidate = base / f"{command}-{stamp}"
    suffix = 0
    while True:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            suffix += 1
            candidate = base / f"{command}-{stamp}-{suffix}"


def _core_asset_paths(plan: CommandPlan, *, home_dir: Path) -> list[tuple[TemplateAsset, Path]]:
    pairs: list[tuple[TemplateAsset, Path]] = []
    for asset in plan.templates:
        if asset.plane != "core":
            continue
        pairs.append((asset, resolve_install_path(asset, home_dir=home_dir)))
    return pairs


def snapshot_core_plane(plan: CommandPlan, *, home_dir: Path, checkpoint_dir: Path) -> dict[str, list[str]]:
    """將現有 core plane 檔案複製到 checkpoint 目錄，供 rollback 還原。

    只備份實際存在的檔案；checkpoint 以相對路徑鏡射 core/systemd 與 core/runtime。
    """
    saved: list[str] = []
    missing: list[str] = []
    for asset, target in _core_asset_paths(plan, home_dir=home_dir):
        if not target.exists():
            missing.append(str(target))
            continue
        relative = Path(asset.target_path)  # e.g. core/systemd/x.service
        dest = checkpoint_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, dest)
        saved.append(str(target))
    manifest = {
        "command": plan.command,
        "instance_name": plan.instance_name,
        "saved": sorted(saved),
        "missing": sorted(missing),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (checkpoint_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"saved": sorted(saved), "missing": sorted(missing)}


def restore_core_from_checkpoint(checkpoint_dir: Path, *, home_dir: Path) -> dict[str, list[str]]:
    """從 checkpoint 還原 core plane 檔案。"""
    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"checkpoint 缺少 manifest：{checkpoint_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for asset, target in _core_asset_paths_from_manifest(checkpoint_dir, home_dir=home_dir):
        if not asset.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, target)
        restored.append(str(target))
    return {"restored": sorted(restored)}


def _core_asset_paths_from_manifest(checkpoint_dir: Path, *, home_dir: Path) -> list[tuple[Path, Path]]:
    """列舉 checkpoint 內的 core 檔案與其還原目標路徑。"""
    pairs: list[tuple[Path, Path]] = []
    for core_sub in ("core/systemd", "core/runtime"):
        sub = checkpoint_dir / core_sub
        if not sub.is_dir():
            continue
        for path in sub.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(checkpoint_dir)
            target = _checkpoint_relative_to_install_path(relative, home_dir=home_dir)
            if target is not None:
                pairs.append((path, target))
    return pairs


def _checkpoint_relative_to_install_path(relative: Path, *, home_dir: Path) -> Path | None:
    parts = relative.parts
    if parts[:2] == ("core", "systemd"):
        return home_dir / ".config" / "systemd" / "user" / relative.name
    if parts[:2] == ("core", "runtime"):
        return home_dir / ".agents" / "core" / "runtime" / relative.name
    return None


def latest_checkpoint(home_dir: Path, *, instance_name: str, command: str | None = None) -> Path | None:
    base = _checkpoint_root(home_dir, instance_name=instance_name)
    if not base.is_dir():
        return None
    candidates = sorted(
        (p for p in base.iterdir() if p.is_dir() and (command is None or p.name.startswith(f"{command}-"))),
        key=lambda p: p.name,
    )
    return candidates[-1] if candidates else None


# ---------------------------------------------------------------------------
# 共用：systemd unit 操作
# ---------------------------------------------------------------------------


def _restart_service_units(plan: CommandPlan) -> list[str]:
    """重啟 plan 的 verify_units；任一失敗即拋錯（由 run_upgrade 觸發 rollback）。

    只把 returncode 記進 report 是 fail-open：新版 unit 起不來時 upgrade 仍會
    回報 `status: ok`，operator 以為升級成功但服務其實是停的。部署面必須
    fail-closed，故 rc 非零直接拋錯。
    """
    actions: list[str] = []
    if not _user_systemd_available():
        return actions
    for unit in plan.verify_units:
        completed = _run_command(["systemctl", "--user", "restart", unit])
        actions.append(f"systemctl --user restart {unit} -> rc={completed.returncode}")
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"systemctl --user restart {unit} 失敗（rc={completed.returncode}）：{detail}"
            )
    return actions


def _stop_service_units(plan: CommandPlan) -> list[str]:
    actions: list[str] = []
    if not _user_systemd_available():
        return actions
    for unit in plan.verify_units:
        completed = _run_command(["systemctl", "--user", "stop", unit])
        actions.append(f"systemctl --user stop {unit} -> rc={completed.returncode}")
    return actions


def _disable_service_units(plan: CommandPlan) -> list[str]:
    actions: list[str] = []
    if not _user_systemd_available():
        return actions
    for unit in plan.verify_units:
        completed = _run_command(["systemctl", "--user", "disable", unit])
        actions.append(f"systemctl --user disable {unit} -> rc={completed.returncode}")
    return actions


def _remove_core_plane(plan: CommandPlan, *, home_dir: Path) -> list[str]:
    removed: list[str] = []
    for asset, target in _core_asset_paths(plan, home_dir=home_dir):
        if target.is_file():
            target.unlink()
            removed.append(str(target))
    return sorted(removed)


# ---------------------------------------------------------------------------
# E3：upgrade 實際執行
# ---------------------------------------------------------------------------


def run_upgrade(*, instance_name: str, root_dir: str, apply: bool, verify: bool, home_dir: str | Path | None = None, version: str | None = None, artifact: str | None = None, artifact_sha256: str | None = None) -> tuple[dict[str, object], int]:
    plan = build_command_plan("upgrade", instance_name=instance_name, root_dir=root_dir)
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else paths.home_root()
    report: dict[str, object] = {
        "command": "upgrade",
        "instance_name": instance_name,
        "root_dir": root_dir,
        "status": "ok",
    }

    if apply:
        artifact_record = _verify_and_record_artifact(artifact=artifact, artifact_sha256=artifact_sha256)
        report["artifact"] = artifact_record

        checkpoint = _new_checkpoint_dir(resolved_home, instance_name=instance_name, command="upgrade")
        snapshot = snapshot_core_plane(plan, home_dir=resolved_home, checkpoint_dir=checkpoint)
        report["checkpoint"] = str(checkpoint)
        report["snapshot"] = snapshot

        try:
            applied = apply_install_plan(plan, home_dir=resolved_home)
            report["applied_files"] = applied["written"]
            report["skipped_existing"] = applied["skipped_existing"]
            report["daemon_reload"] = _run_daemon_reload()
            report["restart"] = _restart_service_units(plan)
            _write_install_record(
                resolved_home,
                instance_name=instance_name,
                command="upgrade",
                version=version,
                artifact=artifact,
                artifact_sha256=artifact_record["sha256"],
            )
        except Exception as exc:
            # E4：升級途中失敗自動 rollback 並標記。
            restore = restore_core_from_checkpoint(checkpoint, home_dir=resolved_home)
            report["status"] = "failed"
            report["error"] = str(exc)
            report["rollback_triggered"] = True
            report["rollback"] = restore
            return report, 1

    if verify:
        verification = verify_install_plan(plan, home_dir=resolved_home)
        report["verification"] = verification
        if verification["status"] != "passed":
            report["status"] = "failed"
            return report, 1

    return report, 0


# ---------------------------------------------------------------------------
# E5：uninstall 實際執行
# ---------------------------------------------------------------------------


def run_uninstall(*, instance_name: str, root_dir: str, apply: bool, home_dir: str | Path | None = None, purge_state: bool = False, purge_secret: bool = False) -> tuple[dict[str, object], int]:
    plan = build_command_plan("uninstall", instance_name=instance_name, root_dir=root_dir)
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else paths.home_root()
    report: dict[str, object] = {
        "command": "uninstall",
        "instance_name": instance_name,
        "root_dir": root_dir,
        "status": "ok",
        "purge_state": purge_state,
        "purge_secret": purge_secret,
    }

    if apply:
        checkpoint = _new_checkpoint_dir(resolved_home, instance_name=instance_name, command="uninstall")
        snapshot = snapshot_core_plane(plan, home_dir=resolved_home, checkpoint_dir=checkpoint)
        report["checkpoint"] = str(checkpoint)
        report["snapshot"] = snapshot

        report["disable"] = _disable_service_units(plan)
        report["stop"] = _stop_service_units(plan)
        report["removed_core_files"] = _remove_core_plane(plan, home_dir=resolved_home)
        report["daemon_reload"] = _run_daemon_reload()

        purged: list[str] = []
        if purge_state:
            purged.extend(_purge_state_plane(plan, home_dir=resolved_home))
        if purge_secret:
            purged.extend(_purge_secret_plane(plan, home_dir=resolved_home))
        report["purged"] = sorted(purged)
        report["preserved_state"] = not purge_state
        report["preserved_secret"] = not purge_secret

    return report, 0


def _purge_state_plane(plan: CommandPlan, *, home_dir: Path) -> list[str]:
    purged: list[str] = []
    for asset in plan.templates:
        if asset.plane != "state":
            continue
        target = resolve_install_path(asset, home_dir=home_dir)
        if target.is_file():
            target.unlink()
            purged.append(str(target))
    return purged


def _purge_secret_plane(plan: CommandPlan, *, home_dir: Path) -> list[str]:
    purged: list[str] = []
    for asset in plan.templates:
        if asset.plane != "secret":
            continue
        target = resolve_install_path(asset, home_dir=home_dir)
        if target.is_file():
            target.unlink()
            purged.append(str(target))
    return purged


# ---------------------------------------------------------------------------
# E4：rollback 入口
# ---------------------------------------------------------------------------


def run_rollback(*, instance_name: str, root_dir: str, home_dir: str | Path | None = None, command: str | None = None) -> tuple[dict[str, object], int]:
    resolved_home = Path(home_dir).expanduser() if home_dir is not None else paths.home_root()
    report: dict[str, object] = {
        "command": "rollback",
        "instance_name": instance_name,
        "root_dir": root_dir,
        "status": "ok",
    }
    checkpoint = latest_checkpoint(resolved_home, instance_name=instance_name, command=command)
    if checkpoint is None:
        report["status"] = "failed"
        report["error"] = "找不到可還原的 checkpoint"
        return report, 1
    report["checkpoint"] = str(checkpoint)
    restore = restore_core_from_checkpoint(checkpoint, home_dir=resolved_home)
    report["restore"] = restore
    return report, 0
