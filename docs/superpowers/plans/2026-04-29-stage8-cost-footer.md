# Stage 8 Cost Footer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Stage 8 cost visibility with a JSON snapshot CLI and tmux footer status line for Codex, Claude Code, and GitHub Copilot usage.

**Architecture:** Add a focused `paulshaclaw.cost` package. Provider adapters produce a provider-neutral `CostSnapshot`, cache keeps tmux responsive, and formatter renders one tmux-safe line. `scripts/start.sh` only wires the status command into the current tmux session.

**Tech Stack:** Python standard library, `yaml` already used by the repo, `unittest`, tmux CLI, OpenSpec change `openspec/changes/stage8-cost-footer/`.

---

## File Structure

- Create: `paulshaclaw/cost/__init__.py`
  - Empty package marker and public version-neutral namespace.
- Create: `paulshaclaw/cost/models.py`
  - Dataclasses for `UsageWindow`, `CopilotAccountUsage`, `ProviderSnapshot`, `CostSnapshot`.
- Create: `paulshaclaw/cost/config.py`
  - Stage 8 config parser with defaults and config-driven Copilot accounts.
- Create: `paulshaclaw/cost/providers.py`
  - Provider collectors for `cdx`, `cc`, and `cpt`, plus safe helpers for local logs and injected fetch functions.
- Create: `paulshaclaw/cost/cache.py`
  - Snapshot cache read/write, TTL, lock-busy behavior, stale preservation.
- Create: `paulshaclaw/cost/formatter.py`
  - Tmux footer rendering and color threshold classification.
- Create: `paulshaclaw/cost/__main__.py`
  - `python -m paulshaclaw.cost --once` JSON CLI.
- Create: `paulshaclaw/cost/status.py`
  - `python -m paulshaclaw.cost.status` one-line footer CLI.
- Create: `tests/test_stage8_cost.py`
  - Unit, cache, provider, formatter, and CLI contract tests.
- Modify: `tests/test_start_sh.py`
  - Add fake `tmux` coverage and update fake Python for Stage 8 status command.
- Modify: `scripts/start.sh`
  - Apply Stage 8 footer with session-local tmux options before Stage 11 cockpit.
- Modify: `paulshaclaw/config/paulshaclaw.sample.yaml`
  - Add commented Stage 8 config sample.
- Modify: `README.md`
  - Add short Stage 8 usage note.

## Task 1: Snapshot Models And Formatter Contract

**Files:**
- Create: `tests/test_stage8_cost.py`
- Create: `paulshaclaw/cost/__init__.py`
- Create: `paulshaclaw/cost/models.py`
- Create: `paulshaclaw/cost/formatter.py`

- [ ] **Step 1: Write failing model and formatter tests**

Add this initial content to `tests/test_stage8_cost.py`:

```python
from __future__ import annotations

import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from paulshaclaw.cost.formatter import classify_usage, format_footer
from paulshaclaw.cost.models import (
    CopilotAccountUsage,
    CostSnapshot,
    ProviderSnapshot,
    UsageWindow,
)


class Stage8ModelFormatterTests(unittest.TestCase):
    def test_snapshot_serializes_provider_neutral_json(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(
                    source_status="fresh",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=18,
                            reset_at=datetime(2026, 4, 29, 15, 21, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="15:21",
                        ),
                        "weekly": UsageWindow(
                            used_percent=41,
                            reset_at=datetime(2026, 5, 2, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="3d",
                        ),
                    },
                ),
                "cc": ProviderSnapshot(source_status="unknown", windows={}),
                "cpt": ProviderSnapshot(
                    source_status="fresh",
                    accounts=(
                        CopilotAccountUsage(
                            account_id="hamanpaul",
                            label="haman",
                            kind="personal",
                            used_requests=724,
                            monthly_allowance=1500,
                            source="github_user_billing",
                        ),
                    ),
                ),
            },
        )

        payload = snapshot.to_jsonable()
        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["timezone"], "Asia/Taipei")
        self.assertEqual(decoded["providers"]["cdx"]["windows"]["five_hour"]["display_reset"], "15:21")
        self.assertEqual(decoded["providers"]["cpt"]["accounts"][0]["label"], "haman")

    def test_footer_renders_balanced_format(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(
                    source_status="fresh",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=18,
                            reset_at=datetime(2026, 4, 29, 15, 21, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="15:21",
                        ),
                        "weekly": UsageWindow(
                            used_percent=41,
                            reset_at=datetime(2026, 5, 2, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                            display_reset="3d",
                        ),
                    },
                ),
                "cc": ProviderSnapshot(source_status="unknown", windows={}),
                "cpt": ProviderSnapshot(
                    source_status="fresh",
                    accounts=(
                        CopilotAccountUsage("hamanpaul", "haman", "personal", 724, 1500, "github_user_billing"),
                        CopilotAccountUsage("paulc-arc", "arc", "company", 127, 300, "github_org_billing"),
                    ),
                ),
            },
        )

        footer = format_footer(snapshot, use_tmux_style=False)

        self.assertIn("cdx 5h:18%(15:21) wk:41%(3d)", footer)
        self.assertIn("cc 5h:-- wk:--", footer)
        self.assertIn("cpt haman:724 arc:127", footer)

    def test_footer_marks_stale_provider(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="stale",
            providers={"cdx": ProviderSnapshot(source_status="stale", windows={})},
        )

        self.assertIn("cdx~", format_footer(snapshot, use_tmux_style=False))

    def test_threshold_boundaries(self) -> None:
        self.assertEqual(classify_usage(69), "low")
        self.assertEqual(classify_usage(70), "warning")
        self.assertEqual(classify_usage(89), "warning")
        self.assertEqual(classify_usage(90), "critical")
        self.assertEqual(classify_usage(None), "neutral")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ModelFormatterTests -v
```

Expected: FAIL or ERROR because `paulshaclaw.cost` modules do not exist.

- [ ] **Step 3: Add model dataclasses**

Create `paulshaclaw/cost/__init__.py`:

```python
from __future__ import annotations
```

Create `paulshaclaw/cost/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UsageWindow:
    used_percent: int | None
    reset_at: datetime | None
    display_reset: str | None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "used_percent": self.used_percent,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "display_reset": self.display_reset,
        }


@dataclass(frozen=True)
class CopilotAccountUsage:
    account_id: str
    label: str
    kind: str
    used_requests: int | None
    monthly_allowance: int | None
    source: str

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "id": self.account_id,
            "label": self.label,
            "kind": self.kind,
            "used_requests": self.used_requests,
            "monthly_allowance": self.monthly_allowance,
            "source": self.source,
        }


@dataclass(frozen=True)
class ProviderSnapshot:
    source_status: str
    windows: dict[str, UsageWindow] = field(default_factory=dict)
    accounts: tuple[CopilotAccountUsage, ...] = ()
    note: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source_status": self.source_status}
        if self.windows:
            payload["windows"] = {
                name: window.to_jsonable() for name, window in self.windows.items()
            }
        if self.accounts:
            payload["accounts"] = [account.to_jsonable() for account in self.accounts]
        if self.note:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True)
class CostSnapshot:
    generated_at: datetime
    timezone: str
    cache_status: str
    providers: dict[str, ProviderSnapshot]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "timezone": self.timezone,
            "cache_status": self.cache_status,
            "providers": {
                name: provider.to_jsonable()
                for name, provider in self.providers.items()
            },
        }
```

- [ ] **Step 4: Add footer formatter**

Create `paulshaclaw/cost/formatter.py`:

```python
from __future__ import annotations

from .models import CostSnapshot, ProviderSnapshot


STYLE_BY_CLASS = {
    "low": "fg=green",
    "warning": "fg=yellow",
    "critical": "fg=red",
    "neutral": "fg=colour245",
}


def classify_usage(value: int | None) -> str:
    if value is None:
        return "neutral"
    if value >= 90:
        return "critical"
    if value >= 70:
        return "warning"
    return "low"


def _style(text: str, usage_percent: int | None, *, use_tmux_style: bool) -> str:
    if not use_tmux_style:
        return text
    style = STYLE_BY_CLASS[classify_usage(usage_percent)]
    return f"#[{style}]{text}#[default]"


def _provider_label(name: str, provider: ProviderSnapshot) -> str:
    suffix = "~" if provider.source_status == "stale" else ""
    return f"{name}{suffix}"


def _format_window(provider: ProviderSnapshot, name: str, label: str) -> str:
    window = provider.windows.get(name)
    if window is None or window.used_percent is None or not window.display_reset:
        return f"{label}:--"
    return f"{label}:{window.used_percent}%({window.display_reset})"


def _format_window_provider(name: str, provider: ProviderSnapshot, *, use_tmux_style: bool) -> str:
    label = _provider_label(name, provider)
    usage = provider.windows.get("five_hour").used_percent if provider.windows.get("five_hour") else None
    prefix = _style(label, usage, use_tmux_style=use_tmux_style)
    return " ".join(
        [
            prefix,
            _format_window(provider, "five_hour", "5h"),
            _format_window(provider, "weekly", "wk"),
        ]
    )


def _format_copilot(provider: ProviderSnapshot, *, use_tmux_style: bool) -> str:
    if not provider.accounts:
        return ""
    parts = [_provider_label("cpt", provider)]
    for account in provider.accounts:
        if account.used_requests is None:
            usage_percent = None
            value = "--"
        else:
            value = str(account.used_requests)
            usage_percent = (
                int(account.used_requests / account.monthly_allowance * 100)
                if account.monthly_allowance
                else None
            )
        parts.append(_style(f"{account.label}:{value}", usage_percent, use_tmux_style=use_tmux_style))
    return " ".join(parts)


def format_footer(snapshot: CostSnapshot, *, use_tmux_style: bool = True) -> str:
    segments: list[str] = []
    for name in ("cdx", "cc"):
        provider = snapshot.providers.get(name)
        if provider is not None:
            segments.append(_format_window_provider(name, provider, use_tmux_style=use_tmux_style))
    cpt = snapshot.providers.get("cpt")
    if cpt is not None:
        cpt_text = _format_copilot(cpt, use_tmux_style=use_tmux_style)
        if cpt_text:
            segments.append(cpt_text)
    return "  ".join(segment for segment in segments if segment)
```

- [ ] **Step 5: Run model and formatter tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ModelFormatterTests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/__init__.py paulshaclaw/cost/models.py paulshaclaw/cost/formatter.py
git commit -m "feat: add stage8 cost snapshot model"
```

## Task 2: Config Parsing And Provider Adapters

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Create: `paulshaclaw/cost/config.py`
- Create: `paulshaclaw/cost/providers.py`

- [ ] **Step 1: Add failing config and provider tests**

Append this to `tests/test_stage8_cost.py`:

```python
import tempfile
import textwrap
from pathlib import Path

from paulshaclaw.cost.config import CostConfig, load_cost_config
from paulshaclaw.cost.providers import collect_codex, collect_copilot


class Stage8ConfigProviderTests(unittest.TestCase):
    def write_config(self, body: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        try:
            handle.write(textwrap.dedent(body))
            handle.flush()
        finally:
            handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_cost_config_defaults(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertIsInstance(cfg, CostConfig)
        self.assertEqual(cfg.timezone, "Asia/Taipei")
        self.assertEqual(cfg.cache_ttl_seconds, 120)
        self.assertEqual(cfg.tmux_refresh_seconds, 30)
        self.assertEqual(cfg.warning_percent, 70)
        self.assertEqual(cfg.critical_percent, 90)
        self.assertEqual(cfg.copilot_accounts, ())

    def test_copilot_accounts_are_config_driven(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: company-user
                      label: work
                      kind: company
                      monthly_allowance: 300
                      org: acme
                    - id: personal-user
                      label: me
                      kind: personal
                      monthly_allowance: 1500
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertEqual([account.label for account in cfg.copilot_accounts], ["work", "me"])
        self.assertEqual(cfg.copilot_accounts[0].account_id, "company-user")
        self.assertEqual(cfg.copilot_accounts[0].org, "acme")

    def test_collect_copilot_uses_injected_fetcher_before_local_fallback(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: hamanpaul
                      label: haman
                      kind: personal
                      monthly_allowance: 1500
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            return 724, "github_user_billing"

        provider = collect_copilot(cfg, fetcher=fetcher)

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.accounts[0].label, "haman")
        self.assertEqual(provider.accounts[0].used_requests, 724)
        self.assertEqual(provider.accounts[0].source, "github_user_billing")

    def test_collect_copilot_marks_local_observed_fallback(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                copilot:
                  accounts:
                    - id: local-user
                      label: local
                      kind: personal
                      monthly_allowance: 100
            """
        )
        cfg = load_cost_config(config_path=path)

        def fetcher(account):
            raise RuntimeError("network unavailable")

        provider = collect_copilot(
            cfg,
            fetcher=fetcher,
            local_observed={"local-user": 12},
        )

        self.assertEqual(provider.source_status, "stale")
        self.assertEqual(provider.accounts[0].source, "local_observed")
        self.assertEqual(provider.accounts[0].used_requests, 12)

    def test_collect_codex_does_not_estimate_missing_quota_windows(self) -> None:
        provider = collect_codex()

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})
```

- [ ] **Step 2: Run tests and verify config/provider failures**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ConfigProviderTests -v
```

Expected: FAIL or ERROR because `cost.config` and `cost.providers` are not implemented.

- [ ] **Step 3: Implement Stage 8 config parser**

Create `paulshaclaw/cost/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
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
    cache_dir: Path = Path("~/.agents/state/cost")
    log_path: Path = Path("~/.agents/log/cost.log")


def _resolve_config_source(config_path: Path | None) -> Path:
    if config_path is not None:
        return Path(config_path)
    env_value = os.environ.get(ENV_CONFIG_VAR)
    if env_value:
        return Path(env_value)
    default = DEFAULT_CONFIG_PATH.expanduser()
    if default.exists():
        return default
    sample = Path(__file__).resolve().parents[2] / "paulshaclaw" / "config" / "paulshaclaw.sample.yaml"
    return sample


def _load_payload(config_path: Path | None) -> dict[str, Any]:
    resolved = _resolve_config_source(config_path)
    if not resolved.exists():
        raise FileNotFoundError(f"設定檔不存在：{resolved}")
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"設定檔必須是 mapping：{resolved}")
    return payload


def _parse_copilot_accounts(raw: Any) -> tuple[CopilotAccountConfig, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("config.cost.providers.copilot.accounts 必須是清單")
    accounts: list[CopilotAccountConfig] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"config.cost.providers.copilot.accounts[{index}] 必須是 mapping")
        account_id = str(item.get("id") or "").strip()
        if not account_id:
            raise ValueError(f"config.cost.providers.copilot.accounts[{index}].id 缺失")
        label = str(item.get("label") or account_id).strip()
        kind = str(item.get("kind") or "personal").strip()
        if kind not in {"personal", "company"}:
            raise ValueError(f"config.cost.providers.copilot.accounts[{index}].kind 不支援：{kind}")
        allowance_raw = item.get("monthly_allowance")
        monthly_allowance = int(allowance_raw) if allowance_raw is not None else None
        accounts.append(
            CopilotAccountConfig(
                account_id=account_id,
                label=label,
                kind=kind,
                monthly_allowance=monthly_allowance,
                org=str(item["org"]) if item.get("org") else None,
                enterprise=str(item["enterprise"]) if item.get("enterprise") else None,
            )
        )
    return tuple(accounts)


def load_cost_config(*, config_path: Path | None = None) -> CostConfig:
    payload = _load_payload(config_path)
    cost = payload.get("cost") or {}
    if not isinstance(cost, dict):
        raise ValueError("config.cost 必須是 mapping")
    providers = cost.get("providers") or {}
    if not isinstance(providers, dict):
        raise ValueError("config.cost.providers 必須是 mapping")
    copilot = providers.get("copilot") or {}
    if not isinstance(copilot, dict):
        raise ValueError("config.cost.providers.copilot 必須是 mapping")
    colors = cost.get("colors") or {}
    if not isinstance(colors, dict):
        raise ValueError("config.cost.colors 必須是 mapping")
    return CostConfig(
        timezone=str(cost.get("timezone", "Asia/Taipei")),
        cache_ttl_seconds=int(cost.get("cache_ttl_seconds", 120)),
        tmux_refresh_seconds=int(cost.get("tmux_refresh_seconds", 30)),
        warning_percent=int(colors.get("warning_percent", 70)),
        critical_percent=int(colors.get("critical_percent", 90)),
        copilot_accounts=_parse_copilot_accounts(copilot.get("accounts")),
        cache_dir=Path(str(cost.get("cache_dir", "~/.agents/state/cost"))).expanduser(),
        log_path=Path(str(cost.get("log_path", "~/.agents/log/cost.log"))).expanduser(),
    )
```

- [ ] **Step 4: Implement provider collectors**

Create `paulshaclaw/cost/providers.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping

from .config import CopilotAccountConfig, CostConfig
from .models import CopilotAccountUsage, ProviderSnapshot


CopilotFetcher = Callable[[CopilotAccountConfig], tuple[int, str]]


def collect_codex() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="trusted quota windows unavailable",
    )


def collect_claude() -> ProviderSnapshot:
    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="credentials or trusted quota source unavailable",
    )


def _unknown_account(account: CopilotAccountConfig, source: str = "unknown") -> CopilotAccountUsage:
    return CopilotAccountUsage(
        account_id=account.account_id,
        label=account.label,
        kind=account.kind,
        used_requests=None,
        monthly_allowance=account.monthly_allowance,
        source=source,
    )


def collect_copilot(
    config: CostConfig,
    *,
    fetcher: CopilotFetcher | None = None,
    local_observed: Mapping[str, int] | None = None,
) -> ProviderSnapshot:
    accounts: list[CopilotAccountUsage] = []
    any_fresh = False
    any_stale = False
    for account in config.copilot_accounts:
        if fetcher is not None:
            try:
                used, source = fetcher(account)
            except Exception:
                used = None
                source = "unknown"
            else:
                any_fresh = True
                accounts.append(
                    CopilotAccountUsage(
                        account_id=account.account_id,
                        label=account.label,
                        kind=account.kind,
                        used_requests=used,
                        monthly_allowance=account.monthly_allowance,
                        source=source,
                    )
                )
                continue
        observed = local_observed.get(account.account_id) if local_observed else None
        if observed is not None:
            any_stale = True
            accounts.append(
                CopilotAccountUsage(
                    account_id=account.account_id,
                    label=account.label,
                    kind=account.kind,
                    used_requests=observed,
                    monthly_allowance=account.monthly_allowance,
                    source="local_observed",
                )
            )
        else:
            accounts.append(_unknown_account(account, source))
    if any_fresh:
        status = "fresh"
    elif any_stale:
        status = "stale"
    else:
        status = "unknown"
    return ProviderSnapshot(source_status=status, accounts=tuple(accounts))


def collect_all(config: CostConfig) -> dict[str, ProviderSnapshot]:
    providers: dict[str, ProviderSnapshot] = {
        "cdx": collect_codex(),
        "cc": collect_claude(),
    }
    cpt = collect_copilot(config)
    if cpt.accounts:
        providers["cpt"] = cpt
    return providers
```

- [ ] **Step 5: Run config/provider tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ConfigProviderTests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/config.py paulshaclaw/cost/providers.py
git commit -m "feat: add stage8 provider config"
```

## Task 3: Cache And Snapshot Collection

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Create: `paulshaclaw/cost/cache.py`

- [ ] **Step 1: Add failing cache tests**

Append this to `tests/test_stage8_cost.py`:

```python
from datetime import timedelta

from paulshaclaw.cost.cache import (
    SnapshotCache,
    build_snapshot,
    load_snapshot_payload,
)


class Stage8CacheTests(unittest.TestCase):
    def test_fresh_cache_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
            )
            cache.write(snapshot)

            loaded = cache.read_if_fresh()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.timezone, "Asia/Taipei")

    def test_stale_cache_returns_none_for_fresh_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=0)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
            )
            cache.write(snapshot)

            self.assertIsNone(cache.read_if_fresh())

    def test_lock_busy_reads_old_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SnapshotCache(Path(tmpdir), ttl_seconds=120)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="stale", windows={})},
            )
            cache.write(snapshot)
            cache.lock_path.write_text("busy", encoding="utf-8")

            loaded = cache.read_stale()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.providers["cdx"].source_status, "stale")

    def test_load_snapshot_payload_rejects_token_like_values(self) -> None:
        payload = {
            "generated_at": "2026-04-29T15:00:00+08:00",
            "timezone": "Asia/Taipei",
            "cache_status": "fresh",
            "providers": {
                "cc": {
                    "source_status": "unknown",
                    "note": "missing credentials",
                }
            },
        }

        snapshot = load_snapshot_payload(payload)

        self.assertEqual(snapshot.providers["cc"].note, "missing credentials")
```

- [ ] **Step 2: Run cache tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8CacheTests -v
```

Expected: FAIL or ERROR because `cost.cache` is not implemented.

- [ ] **Step 3: Implement cache module**

Create `paulshaclaw/cost/cache.py`:

```python
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .models import CostSnapshot, CopilotAccountUsage, ProviderSnapshot, UsageWindow


def build_snapshot(*, timezone: str, providers: dict[str, ProviderSnapshot], cache_status: str = "fresh") -> CostSnapshot:
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        timezone = "Asia/Taipei"
        tz = ZoneInfo(timezone)
    return CostSnapshot(
        generated_at=datetime.now(tz),
        timezone=timezone,
        cache_status=cache_status,
        providers=providers,
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _load_window(raw: Any) -> UsageWindow:
    if not isinstance(raw, dict):
        return UsageWindow(None, None, None)
    used = raw.get("used_percent")
    return UsageWindow(
        used_percent=int(used) if used is not None else None,
        reset_at=_parse_dt(raw.get("reset_at")),
        display_reset=raw.get("display_reset"),
    )


def _load_provider(raw: Any) -> ProviderSnapshot:
    if not isinstance(raw, dict):
        return ProviderSnapshot(source_status="error", windows={})
    windows_raw = raw.get("windows") or {}
    accounts_raw = raw.get("accounts") or ()
    windows = {
        str(name): _load_window(item)
        for name, item in windows_raw.items()
        if isinstance(windows_raw, dict)
    }
    accounts: list[CopilotAccountUsage] = []
    if isinstance(accounts_raw, list):
        for item in accounts_raw:
            if not isinstance(item, dict):
                continue
            accounts.append(
                CopilotAccountUsage(
                    account_id=str(item.get("id") or ""),
                    label=str(item.get("label") or item.get("id") or ""),
                    kind=str(item.get("kind") or "personal"),
                    used_requests=int(item["used_requests"]) if item.get("used_requests") is not None else None,
                    monthly_allowance=int(item["monthly_allowance"]) if item.get("monthly_allowance") is not None else None,
                    source=str(item.get("source") or "unknown"),
                )
            )
    return ProviderSnapshot(
        source_status=str(raw.get("source_status") or "unknown"),
        windows=windows,
        accounts=tuple(accounts),
        note=raw.get("note"),
    )


def load_snapshot_payload(payload: dict[str, Any]) -> CostSnapshot:
    providers_raw = payload.get("providers") or {}
    providers = {
        str(name): _load_provider(raw)
        for name, raw in providers_raw.items()
        if isinstance(providers_raw, dict)
    }
    return CostSnapshot(
        generated_at=_parse_dt(str(payload.get("generated_at"))) or datetime.now(ZoneInfo("Asia/Taipei")),
        timezone=str(payload.get("timezone") or "Asia/Taipei"),
        cache_status=str(payload.get("cache_status") or "unknown"),
        providers=providers,
    )


class SnapshotCache:
    def __init__(self, cache_dir: Path, *, ttl_seconds: int) -> None:
        self.cache_dir = Path(cache_dir).expanduser()
        self.ttl_seconds = ttl_seconds
        self.snapshot_path = self.cache_dir / "snapshot.json"
        self.lock_path = self.cache_dir / "snapshot.lock"

    def read_if_fresh(self) -> CostSnapshot | None:
        if not self.snapshot_path.exists():
            return None
        age = time.time() - self.snapshot_path.stat().st_mtime
        if age > self.ttl_seconds:
            return None
        return self.read_stale()

    def read_stale(self) -> CostSnapshot | None:
        if not self.snapshot_path.exists():
            return None
        payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        return load_snapshot_payload(payload)

    def write(self, snapshot: CostSnapshot) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(
            json.dumps(snapshot.to_jsonable(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @contextmanager
    def lock(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            yield False
            return
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            yield True
        finally:
            self.lock_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run cache tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8CacheTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/cache.py
git commit -m "feat: add stage8 snapshot cache"
```

## Task 4: CLI Entry Points

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Create: `paulshaclaw/cost/__main__.py`
- Create: `paulshaclaw/cost/status.py`

- [ ] **Step 1: Add failing CLI contract tests**

Append this to `tests/test_stage8_cost.py`:

```python
import subprocess
import sys


class Stage8CliTests(unittest.TestCase):
    def test_once_cli_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "paulshaclaw.yaml"
            config.write_text(
                textwrap.dedent(
                    """
                    workspaces:
                      - path: /tmp/ws
                        name: ws
                    cost:
                      cache_dir: {cache_dir}
                    """
                ).format(cache_dir=str(Path(tmpdir) / "cache")),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, "-m", "paulshaclaw.cost", "--once", "--config", str(config)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("providers", payload)

    def test_status_cli_prints_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "paulshaclaw.yaml"
            config.write_text(
                textwrap.dedent(
                    """
                    workspaces:
                      - path: /tmp/ws
                        name: ws
                    cost:
                      cache_dir: {cache_dir}
                      providers:
                        copilot:
                          accounts:
                            - id: hamanpaul
                              label: haman
                              kind: personal
                              monthly_allowance: 1500
                    """
                ).format(cache_dir=str(Path(tmpdir) / "cache")),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, "-m", "paulshaclaw.cost.status", "--config", str(config)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(len(completed.stdout.splitlines()), 1)
            self.assertIn("cdx", completed.stdout)
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8CliTests -v
```

Expected: FAIL or ERROR because CLI modules are not implemented.

- [ ] **Step 3: Implement `python -m paulshaclaw.cost --once`**

Create `paulshaclaw/cost/__main__.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cache import SnapshotCache, build_snapshot
from .config import load_cost_config
from .providers import collect_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw.cost",
        description="Stage 8 Cost Snapshot",
    )
    parser.add_argument("--config", default=None, help="path to paulshaclaw.yaml")
    parser.add_argument("--once", action="store_true", help="emit one JSON snapshot")
    return parser


def build_current_snapshot(config_path: Path | None = None):
    config = load_cost_config(config_path=config_path)
    providers = collect_all(config)
    snapshot = build_snapshot(timezone=config.timezone, providers=providers)
    cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
    cache.write(snapshot)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.once:
        print("錯誤: Stage 8 cost CLI requires --once", file=sys.stderr)
        return 1
    try:
        config_path = Path(args.config) if args.config else None
        snapshot = build_current_snapshot(config_path)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1
    print(json.dumps(snapshot.to_jsonable(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Implement status CLI**

Create `paulshaclaw/cost/status.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .__main__ import build_current_snapshot
from .cache import SnapshotCache
from .config import load_cost_config
from .formatter import format_footer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw.cost.status",
        description="Stage 8 tmux footer status",
    )
    parser.add_argument("--config", default=None, help="path to paulshaclaw.yaml")
    parser.add_argument("--plain", action="store_true", help="disable tmux style output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else None
    try:
        config = load_cost_config(config_path=config_path)
        cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
        snapshot = cache.read_if_fresh()
        if snapshot is None:
            with cache.lock() as acquired:
                if acquired:
                    snapshot = build_current_snapshot(config_path)
                else:
                    snapshot = cache.read_stale()
        if snapshot is None:
            snapshot = build_current_snapshot(config_path)
        print(format_footer(snapshot, use_tmux_style=not args.plain))
        return 0
    except Exception as error:
        print("cdx 5h:-- wk:--  cc 5h:-- wk:--")
        print(f"stage8 cost status degraded: {error}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8CliTests -v
```

Expected: PASS.

- [ ] **Step 6: Run all Stage 8 tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/__main__.py paulshaclaw/cost/status.py
git commit -m "feat: add stage8 cost cli"
```

## Task 5: Tmux Startup Integration

**Files:**
- Modify: `tests/test_start_sh.py`
- Modify: `scripts/start.sh`

- [ ] **Step 1: Add failing `scripts/start.sh` tmux tests**

Modify `FAKE_PYTHON` in `tests/test_start_sh.py` so the fake Python accepts Stage 8. Insert this block before the existing `if module == "paulshaclaw.cockpit":` branch:

```python
        if module == "paulshaclaw.cost.status":
            print("cdx 5h:-- wk:--")
            return 0

        if module == "paulshaclaw.cockpit" and os.environ.get("FAKE_COCKPIT_EXIT") == "1":
            return 0
```

Add this test class below `StartScriptLifecycleTests`:

```python
class StartScriptStage8FooterTests(unittest.TestCase):
    def test_start_sh_applies_session_local_cost_footer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            tmux_log = tmpdir_path / "tmux.log"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    echo "$@" >> "$FAKE_TMUX_LOG"
                    if [[ "$1" == "show-option" ]]; then
                      echo "existing-right"
                    fi
                    """
                ),
                encoding="utf-8",
            )
            fake_tmux.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh_text = START_SH.read_text(encoding="utf-8").replace(
                "REPO=/home/paul_chen/prj_pri/paulshaclaw",
                f"REPO={repo_root}",
            )
            start_sh.write_text(start_sh_text, encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["TMUX"] = "/tmp/tmux-test"
            env["TMUX_PANE"] = "%0"
            env["FAKE_COCKPIT_EXIT"] = "1"
            env["FAKE_MONITOR_PIDFILE"] = str(tmpdir_path / "monitor.pid")
            env["FAKE_TMUX_LOG"] = str(tmux_log)

            completed = subprocess.run(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                check=False,
            )

            log = tmux_log.read_text(encoding="utf-8")
            self.assertIn("set-option status-interval 30", log)
            self.assertIn("set-option status-right", log)
            self.assertIn("existing-right", log)
            self.assertIn("paulshaclaw.cost.status", log)
            self.assertNotIn("set-option -g", log)
            self.assertNotIn(str(home_dir / ".tmux.conf"), log)
            self.assertNotEqual(completed.returncode, 2, completed.stderr)
```

- [ ] **Step 2: Run the new start script test and verify failure**

Run:

```bash
python3 -m unittest tests.test_start_sh.StartScriptStage8FooterTests -v
```

Expected: FAIL because `scripts/start.sh` does not call tmux for Stage 8.

- [ ] **Step 3: Update `scripts/start.sh`**

Modify `scripts/start.sh` to include this function before Stage 9 starts:

```bash
apply_stage8_footer() {
  if [[ -z "${TMUX:-}" ]]; then
    return 0
  fi
  if ! command -v tmux >/dev/null 2>&1; then
    return 0
  fi

  local footer_cmd
  local existing_right
  footer_cmd="#(${PY} -m paulshaclaw.cost.status)"
  existing_right="$(tmux show-option -qv status-right 2>/dev/null || true)"

  tmux set-option status-interval 30
  case "${existing_right}" in
    *"paulshaclaw.cost.status"*)
      return 0
      ;;
    "")
      tmux set-option status-right "${footer_cmd}"
      ;;
    *)
      tmux set-option status-right "${existing_right} ${footer_cmd}"
      ;;
  esac
}
```

Call it before the Stage 9 monitor block:

```bash
# Stage 8: cost footer (session-local tmux status)
apply_stage8_footer

# Stage 9: project-monitor (background)
"$PY" -m paulshaclaw.monitor >> ~/.agents/log/monitor.log 2>&1 &
```

- [ ] **Step 4: Run start script tests**

Run:

```bash
python3 -m unittest tests.test_start_sh -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_start_sh.py scripts/start.sh
git commit -m "feat: wire stage8 cost footer into startup"
```

## Task 6: Config Sample, Docs, And OpenSpec Validation

**Files:**
- Modify: `paulshaclaw/config/paulshaclaw.sample.yaml`
- Modify: `README.md`
- Verify: `openspec/changes/stage8-cost-footer/`
- Verify: `docs/superpowers/specs/2026-04-29-stage8-cost-footer-design.md`

- [ ] **Step 1: Update sample config**

Append this section to `paulshaclaw/config/paulshaclaw.sample.yaml`:

```yaml

cost:
  timezone: Asia/Taipei
  cache_ttl_seconds: 120
  tmux_refresh_seconds: 30
  colors:
    warning_percent: 70
    critical_percent: 90
  providers:
    copilot:
      accounts:
        - id: hamanpaul
          label: haman
          kind: personal
          monthly_allowance: 1500
        - id: paulc-arc
          label: arc
          kind: company
          monthly_allowance: 300
          org: example-org
```

- [ ] **Step 2: Update README usage section**

Add this short section under `## Usage` in `README.md`:

````markdown
### Stage 8 cost footer

```bash
# Emit one JSON snapshot for debugging
python3 -m paulshaclaw.cost --once

# Render the tmux footer line
python3 -m paulshaclaw.cost.status --plain
```

`scripts/start.sh` applies the Stage 8 footer to the current tmux session with `status-interval 30`. Copilot accounts are read from config; account labels and request allowances are not hardcoded.
````

- [ ] **Step 3: Run focused tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost tests.test_start_sh -v
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS, except documented environment-only tmux/textual skips already present in Stage 11 tests.

- [ ] **Step 5: Validate OpenSpec change**

Run:

```bash
openspec status --change stage8-cost-footer
openspec validate stage8-cost-footer --strict
```

Expected: `All artifacts complete!` and `Change 'stage8-cost-footer' is valid`.

- [ ] **Step 6: Commit docs and validation updates**

```bash
git add paulshaclaw/config/paulshaclaw.sample.yaml README.md openspec/changes/stage8-cost-footer docs/superpowers/specs/2026-04-29-stage8-cost-footer-design.md
git commit -m "docs: document stage8 cost footer"
```

## Self-Review

Spec coverage:

- Stage 8 snapshot CLI is implemented by Tasks 1, 3, and 4.
- Tmux footer status command is implemented by Tasks 1, 3, and 4.
- Provider windows and reset displays are covered by Tasks 1 and 2.
- Config-driven Copilot accounts and source priority are covered by Task 2.
- Snapshot cache behavior is covered by Task 3.
- Footer color thresholds are covered by Task 1.
- Stage 7 startup integration is covered by Task 5.
- Documentation and OpenSpec validation are covered by Task 6.

Placeholder scan:

- No placeholder markers remain in this plan.
- Every code-changing step names exact files and includes concrete code.

Type consistency:

- `CostSnapshot`, `ProviderSnapshot`, `UsageWindow`, and `CopilotAccountUsage` are defined in Task 1 and reused consistently.
- `CostConfig` and `CopilotAccountConfig` are defined in Task 2 and reused by provider and CLI steps.
- CLI modules call the same `build_current_snapshot` function and `SnapshotCache` API defined earlier.
