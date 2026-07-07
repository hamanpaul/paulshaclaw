from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from paulshaclaw.config import paths

ENV_CONFIG_VAR = "PAULSHACLAW_CONFIG"
SAMPLE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "paulshaclaw.sample.yaml"
)


def default_config_path() -> Path:
    return paths.config_path("paulshaclaw.yaml")


def default_claude_statusline_sidecar() -> Path:
    return paths.state_path("cost", "claude_rate_limits.json")


def default_codex_auth_path() -> Path:
    return paths.codex_root() / "auth.json"


def default_cost_cache_dir() -> Path:
    return paths.state_path("cost")


def default_cost_log_path() -> Path:
    return paths.log_root() / "cost.log"


@dataclass(frozen=True)
class CopilotAccountConfig:
    account_id: str
    label: str
    kind: str
    monthly_allowance: int | None = None
    org: str | None = None
    enterprise: str | None = None


@dataclass(frozen=True)
class ClaudeProviderConfig:
    statusline_sidecar: Path = field(
        default_factory=default_claude_statusline_sidecar
    )
    max_age_seconds: int = 300
    local_fallback: bool = False


@dataclass(frozen=True)
class CodexProviderConfig:
    enabled: bool = True
    auth_path: Path = field(default_factory=default_codex_auth_path)
    usage_url: str = "https://chatgpt.com/api/codex/usage"
    max_age_seconds: int = 300
    local_fallback: bool = False


@dataclass(frozen=True)
class CostConfig:
    timezone: str = "Asia/Taipei"
    cache_ttl_seconds: int = 120
    tmux_refresh_seconds: int = 30
    warning_percent: int = 70
    critical_percent: int = 90
    copilot_accounts: tuple[CopilotAccountConfig, ...] = ()
    cache_dir: Path = field(default_factory=default_cost_cache_dir)
    log_path: Path = field(default_factory=default_cost_log_path)
    claude: ClaudeProviderConfig = field(default_factory=ClaudeProviderConfig)
    codex: CodexProviderConfig = field(default_factory=CodexProviderConfig)


def _resolve_config_source(config_path: Path | None) -> Path | None:
    if config_path is not None:
        return Path(config_path)
    env_value = os.environ.get(ENV_CONFIG_VAR)
    if env_value:
        return Path(env_value)
    default = default_config_path()
    if default.exists():
        return default
    if SAMPLE_CONFIG_PATH.exists():
        return SAMPLE_CONFIG_PATH
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


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"布林設定值無法解析：{value}")


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


def _parse_claude_provider(raw: Any) -> ClaudeProviderConfig:
    item = _mapping(raw, "config.cost.providers.claude")
    sidecar = item.get("statusline_sidecar")
    max_age = item.get("max_age_seconds")
    return ClaudeProviderConfig(
        statusline_sidecar=(
            Path(str(sidecar)).expanduser()
            if sidecar
            else default_claude_statusline_sidecar()
        ),
        max_age_seconds=int(max_age) if max_age is not None else 300,
        local_fallback=_bool_value(item.get("local_fallback"), default=False),
    )


def _parse_codex_provider(raw: Any) -> CodexProviderConfig:
    item = _mapping(raw, "config.cost.providers.codex")
    auth_path = item.get("auth_path")
    max_age = item.get("max_age_seconds")
    usage_url = item.get("usage_url")
    return CodexProviderConfig(
        enabled=_bool_value(item.get("enabled"), default=True),
        auth_path=(
            Path(str(auth_path)).expanduser()
            if auth_path
            else default_codex_auth_path()
        ),
        usage_url=str(usage_url) if usage_url else "https://chatgpt.com/api/codex/usage",
        max_age_seconds=int(max_age) if max_age is not None else 300,
        local_fallback=_bool_value(item.get("local_fallback"), default=False),
    )


def load_cost_config(*, config_path: Path | None = None) -> CostConfig:
    payload = _load_payload(config_path)

    cost = _mapping(payload.get("cost"), "config.cost")
    providers = _mapping(cost.get("providers"), "config.cost.providers")
    copilot = _mapping(providers.get("copilot"), "config.cost.providers.copilot")
    claude = _mapping(providers.get("claude"), "config.cost.providers.claude")
    codex = _mapping(providers.get("codex"), "config.cost.providers.codex")
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
        claude=_parse_claude_provider(claude),
        codex=_parse_codex_provider(codex),
        cache_dir=(
            Path(str(cache_dir_raw)).expanduser()
            if cache_dir_raw
            else default_cost_cache_dir()
        ),
        log_path=(
            Path(str(log_path_raw)).expanduser()
            if log_path_raw
            else default_cost_log_path()
        ),
    )
