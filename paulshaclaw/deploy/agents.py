from __future__ import annotations

import argparse
import copy
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

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


@dataclass(frozen=True)
class DetectedAgent:
    name: str
    binary: Path | None
    state_present: bool


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


def _state_paths(home: Path) -> dict[str, Path]:
    return {
        "codex": home / ".codex" / "auth.json",
        "claude": home / ".claude",
        "copilot": home / ".config" / "github-copilot",
        "agy": home / ".gemini",
    }


def detect_agents(
    *,
    which: Callable[[str], str | None] = shutil.which,
    home: Path | None = None,
) -> tuple[DetectedAgent, ...]:
    state_paths = _state_paths(_resolve_home(home))
    detected: list[DetectedAgent] = []
    for provider in _FOOTER_PROVIDERS:
        cli_path = which(provider)
        detected.append(
            DetectedAgent(
                name=provider,
                binary=Path(cli_path) if cli_path else None,
                state_present=state_paths[provider].exists(),
            )
        )
    return tuple(detected)


def detected_agents_report(
    detected_agents: Sequence[DetectedAgent],
) -> list[dict[str, object]]:
    report: list[dict[str, object]] = []
    for agent in detected_agents:
        report.append(
            {
                "name": agent.name,
                "binary": str(agent.binary) if agent.binary is not None else None,
                "state_present": agent.state_present,
            }
        )
    return report


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


def _account_enabled(account) -> bool:
    return bool(getattr(account, "enabled", True))


def _missing_yaml_dependency(error: BaseException) -> bool:
    return isinstance(error, ModuleNotFoundError) and error.name == "yaml"


def _default_footer_enabled() -> dict[str, object]:
    return {
        "codex": True,
        "claude": True,
        "copilot": {},
        "agy": False,
    }


def _selection_enabled_fallback(
    selection: dict[str, object] | None,
) -> dict[str, object]:
    if selection is None:
        return _default_footer_enabled()
    selected = selection.get("providers")
    selected = selected if isinstance(selected, dict) else {}
    disable_all = bool(selection.get("disable_all", False))
    copilot_enabled: dict[str, bool] = {}
    copilot = selected.get("copilot")
    if isinstance(copilot, dict) and not disable_all:
        labels = copilot.get("labels")
        if isinstance(labels, list):
            copilot_enabled = {str(label): True for label in labels}
    return {
        "codex": bool(not disable_all and "codex" in selected),
        "claude": bool(not disable_all and "claude" in selected),
        "copilot": copilot_enabled,
        "agy": bool(not disable_all and "agy" in selected),
    }


def _preview_providers(config: CostConfig) -> dict[str, ProviderSnapshot]:
    from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot

    providers: dict[str, ProviderSnapshot] = {}
    if config.codex.enabled:
        providers["cdx"] = ProviderSnapshot(source_status="unknown", source="unknown", windows={})
    if config.claude.enabled:
        providers["cc"] = ProviderSnapshot(source_status="unknown", source="unknown", windows={})

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
        providers["cpt"] = ProviderSnapshot(source_status="unknown", source="unknown", accounts=copilot_accounts)

    if config.agy.enabled:
        providers["agy"] = ProviderSnapshot(source_status="unknown", source="unknown", accounts=())
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


def resolve_footer_enabled(
    *,
    selection: dict[str, object] | None = None,
    payload: dict[str, Any] | None = None,
    home_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, object]:
    from paulshaclaw.cost.config import parse_cost_config_payload

    resolved_payload = payload
    if resolved_payload is None:
        try:
            resolved_payload, _source, _target = load_footer_config_payload(
                home_dir=home_dir,
                config_path=config_path,
            )
        except ModuleNotFoundError as error:
            if _missing_yaml_dependency(error):
                return _selection_enabled_fallback(selection)
            raise
    if selection is not None:
        resolved_payload = apply_footer_selection_payload(resolved_payload, selection)
    config = parse_cost_config_payload(resolved_payload)
    return {
        "codex": config.codex.enabled,
        "claude": config.claude.enabled,
        "copilot": {
            account.account_id: _account_enabled(account)
            for account in config.copilot_accounts
        },
        "agy": config.agy.enabled,
    }


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
    enabled: dict[str, object] | None = None,
    selection: dict[str, object] | None = None,
    reason: str | None = None,
    preview: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {"mode": mode}
    if enabled is not None:
        report["enabled"] = copy.deepcopy(enabled)
    if reason is not None:
        report["reason"] = reason
    if selection is not None and selection.get("raw") is not None:
        report["requested"] = selection.get("raw")
    if preview is not None:
        report["preview"] = preview
    return report


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _next_backup_path(target_path: Path) -> Path:
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    candidate = target_path.parent / f"{target_path.name}.bak-{stamp}"
    index = 1
    while candidate.exists():
        candidate = target_path.parent / f"{target_path.name}.bak-{stamp}-{index}"
        index += 1
    return candidate


def prepare_footer_selection(
    *,
    footer: str | dict[str, object] | None,
    apply: bool,
    home_dir: str | Path | None,
    stdin: object,
    stdout: object,
) -> tuple[tuple[DetectedAgent, ...], dict[str, Any], dict[str, object] | None]:
    home = _resolve_home(home_dir)
    detected = detect_agents(home=home)
    resolved_footer = parse_footer_argument(footer) if isinstance(footer, str) else footer

    if resolved_footer is not None:
        preview: str | None
        try:
            preview = preview_footer_selection(resolved_footer, home_dir=home)
        except Exception:
            preview = None
        enabled = resolve_footer_enabled(
            selection=resolved_footer,
            home_dir=home,
            config_path=None,
        )
        return detected, format_footer_selection_report(
            "flag",
            enabled=enabled,
            selection=resolved_footer,
            preview=preview,
        ), resolved_footer

    if not apply:
        return detected, format_footer_selection_report(
            "skipped",
            reason="plan-only",
        ), None

    if not (_isatty(stdin) and _isatty(stdout)):
        return detected, format_footer_selection_report(
            "skipped",
            reason="no-tty",
        ), None

    from .footer_select import (
        build_selection_options,
        run_footer_selection,
        selection_from_values,
    )
    from paulshaclaw.cost.config import parse_cost_config_payload

    try:
        payload, _source, _target = load_footer_config_payload(home_dir=home)
    except ModuleNotFoundError as error:
        if not _missing_yaml_dependency(error):
            raise
        payload = {}
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
        return detected, format_footer_selection_report(
            "cancelled",
            enabled=resolve_footer_enabled(payload=payload),
        ), None
    preview = preview_footer_selection(selection, payload=payload)
    enabled = resolve_footer_enabled(payload=payload, selection=selection)
    return detected, format_footer_selection_report(
        "tui",
        enabled=enabled,
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
        original_text = target_path.read_text(encoding="utf-8")
        backup_path = _next_backup_path(target_path)
        backup_path.write_text(original_text, encoding="utf-8")

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
