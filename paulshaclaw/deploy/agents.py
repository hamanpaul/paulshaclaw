from __future__ import annotations

import argparse
import copy
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from paulshaclaw.config import paths

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from paulshaclaw.cost.config import CostConfig
    from paulshaclaw.cost.models import ProviderSnapshot

_FOOTER_PROVIDERS = ("codex", "claude", "copilot", "agy")
_NEVER_READ = (
    ".codex/auth.json",
    ".gemini/oauth_creds.json",
    ".gemini/antigravity-oauth-token",
    ".gemini/google_accounts.json",
)


def _isatty(stream: object) -> bool:
    try:
        isatty = getattr(stream, "isatty")
    except Exception:
        return False
    try:
        return bool(isatty())
    except Exception:
        return False


def _resolve_home(home_dir: str | Path | None = None) -> Path:
    if home_dir is not None:
        return Path(home_dir).expanduser()
    return paths.home_root()


def _resolve_config_path(
    *,
    home_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser()
    if home_dir is None:
        return paths.config_path("paulshaclaw.yaml")
    return _resolve_home(home_dir) / ".config" / "paulshaclaw" / "paulshaclaw.yaml"


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    import yaml

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"設定檔解析失敗：{path} ({error})") from error
    if not isinstance(payload, dict):
        raise ValueError(f"設定檔必須是 mapping：{path}")
    return payload


def _ensure_mapping(payload: dict[str, Any], key: str, *, path: str) -> dict[str, Any]:
    value = payload.get(key)
    if value is None:
        value = {}
        payload[key] = value
    if not isinstance(value, dict):
        raise ValueError(f"{path} 必須是 mapping")
    return value


def _ensure_accounts(provider: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    accounts = provider.get("accounts")
    if accounts is None:
        accounts = []
        provider["accounts"] = accounts
    if not isinstance(accounts, list):
        raise ValueError(f"{path} 必須是清單")
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(accounts):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}[{index}] 必須是 mapping")
        normalized.append(entry)
    return normalized


def _state_paths(home: Path) -> dict[str, dict[str, Path]]:
    return {
        "codex": {
            "state_path": home / ".codex" / "auth.json",
        },
        "claude": {
            "state_path": home / ".claude",
            "sidecar_path": home / ".agents" / "state" / "cost" / "claude_rate_limits.json",
        },
        "copilot": {
            "state_path": home / ".config" / "github-copilot",
        },
        "agy": {
            "state_path": home / ".gemini",
        },
    }


def detect_agents(
    *,
    home_dir: str | Path | None = None,
) -> dict[str, dict[str, object]]:
    home = _resolve_home(home_dir)
    state_paths = _state_paths(home)
    detected: dict[str, dict[str, object]] = {}
    for provider in _FOOTER_PROVIDERS:
        cli_path = shutil.which(provider)
        state_path = state_paths[provider]["state_path"]
        state_exists = state_path.exists()
        item: dict[str, object] = {
            "detected": bool(cli_path) and state_exists,
            "cli_path": cli_path,
            "state_path": str(state_path),
            "state_exists": state_exists,
        }
        sidecar_path = state_paths[provider].get("sidecar_path")
        if sidecar_path is not None:
            item["sidecar_path"] = str(sidecar_path)
            item["sidecar_exists"] = sidecar_path.exists()
        detected[provider] = item
    return detected


def parse_footer_argument(raw: str) -> dict[str, object]:
    value = raw.strip()
    if not value:
        raise argparse.ArgumentTypeError("--footer 不可為空")
    if value == "none":
        return {"raw": value, "disable_all": True, "providers": {}}

    parsed: dict[str, dict[str, object]] = {}
    for token in value.split(","):
        item = token.strip()
        if not item:
            raise argparse.ArgumentTypeError("--footer 格式錯誤")
        parts = item.split(":")
        if any(not part for part in parts):
            raise argparse.ArgumentTypeError("--footer 格式錯誤")
        provider, *labels = parts
        if provider == "none":
            raise argparse.ArgumentTypeError("--footer=none 不可與其他 provider 混用")
        if provider not in _FOOTER_PROVIDERS:
            allowed = ", ".join((*_FOOTER_PROVIDERS, "none"))
            raise argparse.ArgumentTypeError(f"--footer 僅支援 {allowed}")
        if provider in parsed:
            raise argparse.ArgumentTypeError(f"--footer 不可重複指定 {provider}")
        if provider == "copilot":
            parsed[provider] = {
                "enabled": True,
                "labels": labels,
                "all_accounts": not labels,
            }
            continue
        if labels:
            raise argparse.ArgumentTypeError(f"{provider} footer 不接受額外 label")
        parsed[provider] = {"enabled": True}

    return {"raw": value, "disable_all": False, "providers": parsed}


def _build_provider_report(selection: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "disable_all": bool(selection.get("disable_all", False)),
        "providers": copy.deepcopy(selection.get("providers", {})),
    }
    if selection.get("raw") is not None:
        report["requested"] = selection.get("raw")
    return report


def _account_enabled(account) -> bool:
    return bool(getattr(account, "enabled", True))


def _preview_providers(config: CostConfig) -> dict[str, ProviderSnapshot]:
    from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot

    providers: dict[str, ProviderSnapshot] = {}
    if config.codex.enabled:
        providers["cdx"] = ProviderSnapshot(source_status="unknown", windows={})
    if config.claude.enabled:
        providers["cc"] = ProviderSnapshot(source_status="unknown", windows={})

    copilot_accounts = tuple(
        CopilotAccountUsage(
            account_id=account.account_id,
            label=account.label,
            kind=account.kind,
            used_requests=None,
            monthly_allowance=account.monthly_allowance,
            source="unknown",
        )
        for account in config.copilot_accounts
        if _account_enabled(account)
    )
    if copilot_accounts:
        providers["cpt"] = ProviderSnapshot(source_status="unknown", accounts=copilot_accounts)

    if config.agy.enabled:
        providers["agy"] = ProviderSnapshot(source_status="unknown", accounts=())
    return providers


def load_footer_config_payload(
    *,
    home_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], str, Path]:
    from paulshaclaw.cost.config import SAMPLE_CONFIG_PATH

    target_path = _resolve_config_path(home_dir=home_dir, config_path=config_path)
    if target_path.is_file():
        return _load_yaml_mapping(target_path), "existing", target_path
    if SAMPLE_CONFIG_PATH.is_file():
        return _load_yaml_mapping(SAMPLE_CONFIG_PATH), "sample", target_path
    return {}, "empty", target_path


def _matching_label(account: Mapping[str, Any]) -> str | None:
    account_id = account.get("id")
    if isinstance(account_id, str) and account_id:
        label = account.get("label")
        if isinstance(label, str) and label:
            return label
        return account_id
    return None


def _set_account_enableds(
    accounts: list[dict[str, Any]],
    *,
    selection_labels: list[str],
    enable_all: bool,
    enabled: bool,
    path: str,
) -> None:
    label_set = set(selection_labels)
    if label_set:
        known_labels: set[str] = set()
        for index, account in enumerate(accounts):
            label = _matching_label(account)
            if label is None:
                raise ValueError(f"{path}[{index}].id 缺失")
            known_labels.add(label)
            account_id = account.get("id")
            if isinstance(account_id, str) and account_id:
                known_labels.add(account_id)
        missing = sorted(label_set - known_labels)
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"{path} 找不到已設定的 label/id：{missing_text}")

    for account in accounts:
        account_id = account.get("id")
        label = _matching_label(account)
        account["enabled"] = bool(
            enabled
            and (
                enable_all
                or not label_set
                or label in label_set
                or (isinstance(account_id, str) and account_id in label_set)
            )
        )


def apply_footer_selection_payload(
    payload: dict[str, Any],
    selection: dict[str, object],
) -> dict[str, Any]:
    updated = copy.deepcopy(payload)
    cost = _ensure_mapping(updated, "cost", path="config.cost")
    providers = _ensure_mapping(cost, "providers", path="config.cost.providers")
    selected = selection.get("providers")
    selected = selected if isinstance(selected, dict) else {}
    disable_all = bool(selection.get("disable_all", False))

    for provider_name in ("codex", "claude", "agy"):
        provider = _ensure_mapping(
            providers,
            provider_name,
            path=f"config.cost.providers.{provider_name}",
        )
        provider["enabled"] = bool(not disable_all and provider_name in selected)

    copilot = _ensure_mapping(providers, "copilot", path="config.cost.providers.copilot")
    copilot_accounts = _ensure_accounts(
        copilot,
        path="config.cost.providers.copilot.accounts",
    )
    copilot_selection = selected.get("copilot") if isinstance(selected.get("copilot"), dict) else {}
    _set_account_enableds(
        copilot_accounts,
        selection_labels=list(copilot_selection.get("labels", [])),
        enable_all=bool(copilot_selection.get("all_accounts", False)),
        enabled=bool(not disable_all and copilot_selection),
        path="config.cost.providers.copilot.accounts",
    )

    agy = _ensure_mapping(providers, "agy", path="config.cost.providers.agy")
    agy_accounts = _ensure_accounts(
        agy,
        path="config.cost.providers.agy.accounts",
    )
    agy_selection = selected.get("agy") if isinstance(selected.get("agy"), dict) else {}
    _set_account_enableds(
        agy_accounts,
        selection_labels=list(agy_selection.get("labels", [])),
        enable_all=bool(agy_selection.get("all_accounts", False) or (agy_selection and not agy_selection.get("labels"))),
        enabled=bool(not disable_all and agy_selection),
        path="config.cost.providers.agy.accounts",
    )
    return updated


def preview_footer_selection(
    selection: dict[str, object],
    *,
    home_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    from paulshaclaw.cost.cache import build_snapshot
    from paulshaclaw.cost.config import parse_cost_config_payload
    from paulshaclaw.cost.formatter import format_footer

    if payload is None:
        payload, _source, _target = load_footer_config_payload(
            home_dir=home_dir,
            config_path=config_path,
        )
    config = parse_cost_config_payload(apply_footer_selection_payload(payload, selection))
    snapshot = build_snapshot(
        timezone=config.timezone,
        providers=_preview_providers(config),
    )
    return format_footer(snapshot, use_tmux_style=False)


def format_footer_selection_report(
    mode: str,
    *,
    selection: dict[str, object] | None = None,
    reason: str | None = None,
    preview: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {"mode": mode}
    if reason is not None:
        report["reason"] = reason
    if selection is not None:
        report.update(_build_provider_report(selection))
    if preview is not None:
        report["preview"] = preview
    return report


def prepare_footer_selection(
    *,
    footer: dict[str, object] | None,
    apply: bool,
    verify: bool,
    home_dir: str | Path | None,
    stdin: object,
    stdout: object,
) -> tuple[dict[str, dict[str, object]], dict[str, Any], dict[str, object] | None]:
    detected = detect_agents(home_dir=home_dir)

    if footer is not None:
        preview: str | None
        try:
            preview = preview_footer_selection(footer, home_dir=home_dir)
        except Exception:
            preview = None
        return detected, format_footer_selection_report(
            "flag",
            selection=footer,
            preview=preview,
        ), footer

    if not apply:
        reason = "plan-only" if not verify else "no-apply"
        return detected, {"mode": "skipped", "reason": reason}, None

    if not (_isatty(stdin) and _isatty(stdout)):
        return detected, {"mode": "skipped", "reason": "no-tty"}, None

    from .footer_select import (
        build_selection_options,
        run_footer_selection,
        selection_from_values,
    )
    from paulshaclaw.cost.config import parse_cost_config_payload

    try:
        payload, _source, _target = load_footer_config_payload(home_dir=home_dir)
    except Exception:
        payload = {}
    config = parse_cost_config_payload(payload)
    options = build_selection_options(detected_agents=detected, config=config)
    selection = run_footer_selection(
        options=options,
        preview_builder=lambda values: preview_footer_selection(
            selection_from_values(values),
            payload=payload,
        ),
    )
    if selection is None:
        return detected, {"mode": "skipped", "reason": "cancelled"}, None
    preview = preview_footer_selection(selection, payload=payload)
    return detected, format_footer_selection_report(
        "interactive",
        selection=selection,
        preview=preview,
    ), selection


def write_footer_config(
    selection: dict[str, object],
    *,
    home_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, object]:
    import yaml

    from paulshaclaw.cost.config import parse_cost_config_payload

    payload, source, target_path = load_footer_config_payload(
        home_dir=home_dir,
        config_path=config_path,
    )
    updated = apply_footer_selection_payload(payload, selection)
    parse_cost_config_payload(updated)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if target_path.is_file():
        backup_path = target_path.with_suffix(f"{target_path.suffix}.bak")
        backup_path.write_text(target_path.read_text(encoding="utf-8"), encoding="utf-8")

    dumped = yaml.safe_dump(updated, allow_unicode=True, sort_keys=False)
    target_path.write_text(dumped, encoding="utf-8")
    preview = preview_footer_selection(selection, payload=updated)
    return {
        "status": "written",
        "path": str(target_path),
        "backup_path": str(backup_path) if backup_path is not None else None,
        "source": source,
        "preview": preview,
    }
