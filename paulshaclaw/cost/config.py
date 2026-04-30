from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("~/.config/paulshaclaw/paulshaclaw.yaml")
ENV_CONFIG_VAR = "PAULSHACLAW_CONFIG"


@dataclass(frozen=True)
class CopilotAccountConfig:
    account_id: str
    label: str
    kind: str
    monthly_allowance: int | None = None
    org: str | None = None
    enterprise: str | None = None


@dataclass(frozen=True)
class CostConfig:
    timezone: str = "Asia/Taipei"
    cache_ttl_seconds: int = 120
    tmux_refresh_seconds: int = 30
    warning_percent: int = 70
    critical_percent: int = 90
    copilot_accounts: tuple[CopilotAccountConfig, ...] = ()
    cache_dir: Path = field(default_factory=lambda: Path("~/.agents/state/cost").expanduser())
    log_path: Path = field(default_factory=lambda: Path("~/.agents/log/cost.log").expanduser())


def _resolve_config_source(config_path: Path | None) -> Path | None:
    if config_path is not None:
        return Path(config_path)
    env_value = os.environ.get(ENV_CONFIG_VAR)
    if env_value:
        return Path(env_value)
    default = DEFAULT_CONFIG_PATH.expanduser()
    if default.exists():
        return default
    return None


def _load_payload(config_path: Path | None) -> dict[str, Any]:
    resolved = _resolve_config_source(config_path)
    if resolved is None:
        return {}
    if not resolved.exists():
        raise FileNotFoundError(f"設定檔不存在：{resolved}")
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"設定檔解析失敗：{resolved} ({error})") from error
    if not isinstance(payload, dict):
        raise ValueError(f"設定檔必須是 mapping：{resolved}")
    return payload


def _mapping(raw: Any, name: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{name} 必須是 mapping")
    return raw


def _parse_copilot_accounts(raw: Any) -> tuple[CopilotAccountConfig, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("config.cost.providers.copilot.accounts 必須是清單")

    items: list[CopilotAccountConfig] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"config.cost.providers.copilot.accounts[{index}] 必須是 mapping")
        account_id = entry.get("id")
        if not account_id:
            raise ValueError(f"config.cost.providers.copilot.accounts[{index}].id 缺失")
        label = entry.get("label", account_id)
        kind = entry.get("kind", "personal")
        if kind not in {"personal", "company"}:
            raise ValueError(
                "config.cost.providers.copilot.accounts"
                f"[{index}].kind 必須是 'personal' 或 'company'"
            )

        monthly_allowance = entry.get("monthly_allowance")
        items.append(
            CopilotAccountConfig(
                account_id=str(account_id),
                label=str(label),
                kind=str(kind),
                monthly_allowance=None if monthly_allowance is None else int(monthly_allowance),
                org=None if entry.get("org") is None else str(entry.get("org")),
                enterprise=(
                    None if entry.get("enterprise") is None else str(entry.get("enterprise"))
                ),
            )
        )
    return tuple(items)


def load_cost_config(*, config_path: Path | None = None) -> CostConfig:
    payload = _load_payload(config_path)

    cost = _mapping(payload.get("cost"), "config.cost")
    providers = _mapping(cost.get("providers"), "config.cost.providers")
    copilot = _mapping(providers.get("copilot"), "config.cost.providers.copilot")
    colors = _mapping(cost.get("colors"), "config.cost.colors")

    cache_dir_raw = cost.get("cache_dir")
    log_path_raw = cost.get("log_path")

    return CostConfig(
        timezone=str(cost.get("timezone", "Asia/Taipei")),
        cache_ttl_seconds=int(cost.get("cache_ttl_seconds", 120)),
        tmux_refresh_seconds=int(cost.get("tmux_refresh_seconds", 30)),
        warning_percent=int(colors.get("warning_percent", 70)),
        critical_percent=int(colors.get("critical_percent", 90)),
        copilot_accounts=_parse_copilot_accounts(copilot.get("accounts")),
        cache_dir=(
            Path(str(cache_dir_raw)).expanduser()
            if cache_dir_raw
            else Path("~/.agents/state/cost").expanduser()
        ),
        log_path=(
            Path(str(log_path_raw)).expanduser()
            if log_path_raw
            else Path("~/.agents/log/cost.log").expanduser()
        ),
    )
