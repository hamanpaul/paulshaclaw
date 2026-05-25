# Fix Stage 8 Footer Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 Stage 8 tmux footer，讓 Copilot、Claude Code、Codex 都能顯示可信用量或以紫色 `?` 清楚標記 local estimated fallback，並排除 Claude gemma4/vLLM 地端用量。

**Architecture:** 保留既有 `CostSnapshot` / `ProviderSnapshot` / `UsageWindow` 與 `format_footer()` 資料流，將變更集中在 provider collectors、provider config、formatter estimated 樣式、status degraded path、cache permission。所有 provider 先嘗試可信來源，失敗才嘗試 local fallback；local fallback 一律標 `source_status="estimated"`，下一次可信來源成功時自然覆蓋 snapshot。

**Tech Stack:** Python stdlib (`unittest`, `pathlib`, `json`, `urllib`, `datetime`, `stat`, `os`), PyYAML for config, OpenSpec change `openspec/changes/fix-stage8-footer-usage`.

---

## File Structure

- Modify: `tests/test_stage8_cost.py` — TDD coverage for estimated rendering, provider config parsing, Claude/Codex collectors, Copilot month filtering, degraded cpt display, cache permissions.
- Modify: `paulshaclaw/cost/formatter.py` — add estimated `?` suffix and purple estimated style.
- Modify: `paulshaclaw/cost/config.py` — add backward-compatible `ClaudeProviderConfig` and `CodexProviderConfig`.
- Modify: `paulshaclaw/cost/providers.py` — implement Claude sidecar reader, Codex quota reader, local estimated fallback helpers, Copilot current-month fallback.
- Modify: `paulshaclaw/cost/status.py` — keep configured Copilot accounts visible in degraded snapshots and dynamic fallback.
- Modify: `paulshaclaw/cost/cache.py` — ensure owner-only cache directory permissions.
- Modify: `docs/superpowers/specs/2026-04-29-stage8-cost-footer-design.md` — remove/update wording that says Claude/Codex are only stubs.
- Verify: `openspec/changes/fix-stage8-footer-usage/*` — already created proposal/design/spec/tasks; keep them in the branch.

## Task 1: Estimated Footer Rendering

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/formatter.py`

- [ ] **Step 1: Write failing formatter tests**

Add these tests in `Stage8ModelFormatterTests` after `test_footer_marks_stale_provider`:

```python
    def test_footer_marks_estimated_provider_with_question_suffix(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cc": ProviderSnapshot(
                    source_status="estimated",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=35,
                            reset_at=None,
                            display_reset="2h",
                        ),
                    },
                )
            },
        )

        footer = format_footer(snapshot, use_tmux_style=False)

        self.assertIn("cc? 5h:35%(2h) wk:--", footer)

    def test_footer_uses_estimated_tmux_style(self) -> None:
        snapshot = CostSnapshot(
            generated_at=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            timezone="Asia/Taipei",
            cache_status="fresh",
            providers={
                "cdx": ProviderSnapshot(
                    source_status="estimated",
                    windows={
                        "five_hour": UsageWindow(
                            used_percent=91,
                            reset_at=None,
                            display_reset="1h",
                        ),
                    },
                )
            },
        )

        footer = format_footer(snapshot)

        self.assertIn("cdx?", footer)
        self.assertIn("#[fg=magenta]91%(1h)#[default]", footer)
        self.assertNotIn("#[fg=red]91%(1h)#[default]", footer)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd /home/paul_chen/prj_pri/paulshaclaw/.worktrees/stage8-footer-usage
python3 -m unittest \
  tests.test_stage8_cost.Stage8ModelFormatterTests.test_footer_marks_estimated_provider_with_question_suffix \
  tests.test_stage8_cost.Stage8ModelFormatterTests.test_footer_uses_estimated_tmux_style \
  -v
```

Expected: both tests fail because `estimated` currently renders without `?` and uses threshold color.

- [ ] **Step 3: Implement minimal formatter changes**

Edit `paulshaclaw/cost/formatter.py`:

```python
TMUX_COLOR_BY_LEVEL = {
    "low": "fg=green",
    "warning": "fg=yellow",
    "critical": "fg=red",
    "neutral": "fg=colour245",
    "estimated": "fg=magenta",
}


def _provider_label(name: str, provider: ProviderSnapshot) -> str:
    if provider.source_status == "stale":
        return f"{name}~"
    if provider.source_status == "estimated":
        return f"{name}?"
    return name


def _provider_window_level(provider: ProviderSnapshot, value: int | None) -> str:
    if provider.source_status == "estimated" and value is not None:
        return "estimated"
    return classify_usage(value)


def _format_window(
    window: UsageWindow | None,
    use_tmux_style: bool,
    *,
    provider: ProviderSnapshot,
) -> str:
    if window is None or window.used_percent is None or not window.display_reset:
        return _wrap("--", "neutral", use_tmux_style)
    text = f"{window.used_percent}%({window.display_reset})"
    return _wrap(text, _provider_window_level(provider, window.used_percent), use_tmux_style)


def _account_level(provider: ProviderSnapshot, account: CopilotAccountUsage) -> str:
    if provider.source_status == "estimated" and account.used_requests is not None:
        return "estimated"
    if account.used_requests is None or not account.monthly_allowance:
        return "neutral"
    percent = int((account.used_requests / account.monthly_allowance) * 100)
    return classify_usage(percent)
```

Update callers:

```python
def _format_window_provider(name: str, provider: ProviderSnapshot, use_tmux_style: bool) -> str:
    windows = provider.windows
    return (
        f"{_provider_label(name, provider)} "
        f"5h:{_format_window(windows.get('five_hour'), use_tmux_style, provider=provider)} "
        f"wk:{_format_window(windows.get('weekly'), use_tmux_style, provider=provider)}"
    )


def _format_copilot_provider(name: str, provider: ProviderSnapshot, use_tmux_style: bool) -> str:
    parts = [_provider_label(name, provider)]
    for account in provider.accounts:
        used = "--" if account.used_requests is None else str(account.used_requests)
        parts.append(_wrap(f"{account.label}:{used}", _account_level(provider, account), use_tmux_style))
    return " ".join(parts)
```

- [ ] **Step 4: Run formatter tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ModelFormatterTests -v
```

Expected: all formatter tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/formatter.py
git commit -m "feat(stage8): mark estimated footer values"
```

## Task 2: Provider Config for Claude and Codex

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/config.py`

- [ ] **Step 1: Write failing config test**

Update import in `tests/test_stage8_cost.py`:

```python
from paulshaclaw.cost.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    CostConfig,
    load_cost_config,
)
```

Add this test in `Stage8ConfigProviderTests` after `test_copilot_account_defaults_label_and_kind`:

```python
    def test_claude_and_codex_provider_config_are_parsed(self) -> None:
        path = self.write_config(
            """
            workspaces:
              - path: /tmp/ws
                name: ws
            cost:
              providers:
                claude:
                  statusline_sidecar: /tmp/claude-rate.json
                  max_age_seconds: 90
                  local_fallback: true
                codex:
                  enabled: true
                  auth_path: /tmp/codex-auth.json
                  usage_url: https://chatgpt.com/api/codex/usage
                  max_age_seconds: 45
                  local_fallback: true
            """
        )

        cfg = load_cost_config(config_path=path)

        self.assertEqual(cfg.claude.statusline_sidecar, Path("/tmp/claude-rate.json"))
        self.assertEqual(cfg.claude.max_age_seconds, 90)
        self.assertTrue(cfg.claude.local_fallback)
        self.assertTrue(cfg.codex.enabled)
        self.assertEqual(cfg.codex.auth_path, Path("/tmp/codex-auth.json"))
        self.assertEqual(cfg.codex.usage_url, "https://chatgpt.com/api/codex/usage")
        self.assertEqual(cfg.codex.max_age_seconds, 45)
        self.assertTrue(cfg.codex.local_fallback)

    def test_claude_and_codex_provider_config_defaults_are_safe(self) -> None:
        cfg = CostConfig()

        self.assertIsInstance(cfg.claude, ClaudeProviderConfig)
        self.assertIsInstance(cfg.codex, CodexProviderConfig)
        self.assertEqual(
            cfg.claude.statusline_sidecar,
            Path("~/.agents/state/cost/claude_rate_limits.json").expanduser(),
        )
        self.assertTrue(cfg.codex.enabled)
        self.assertEqual(cfg.codex.auth_path, Path("~/.codex/auth.json").expanduser())
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_claude_and_codex_provider_config_are_parsed \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_claude_and_codex_provider_config_defaults_are_safe \
  -v
```

Expected: import or attribute failure because config dataclasses do not exist.

- [ ] **Step 3: Implement config dataclasses and parsing**

Edit `paulshaclaw/cost/config.py` after `CopilotAccountConfig`:

```python
@dataclass(frozen=True)
class ClaudeProviderConfig:
    statusline_sidecar: Path = field(
        default_factory=lambda: Path("~/.agents/state/cost/claude_rate_limits.json").expanduser()
    )
    max_age_seconds: int = 300
    local_fallback: bool = False


@dataclass(frozen=True)
class CodexProviderConfig:
    enabled: bool = True
    auth_path: Path = field(default_factory=lambda: Path("~/.codex/auth.json").expanduser())
    usage_url: str = "https://chatgpt.com/api/codex/usage"
    max_age_seconds: int = 300
    local_fallback: bool = False
```

Extend `CostConfig`:

```python
    claude: ClaudeProviderConfig = field(default_factory=ClaudeProviderConfig)
    codex: CodexProviderConfig = field(default_factory=CodexProviderConfig)
```

Add helpers near `_parse_copilot_accounts`:

```python
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


def _parse_claude_provider(raw: Any) -> ClaudeProviderConfig:
    item = _mapping(raw, "config.cost.providers.claude")
    sidecar = item.get("statusline_sidecar")
    max_age = item.get("max_age_seconds")
    return ClaudeProviderConfig(
        statusline_sidecar=(
            Path(str(sidecar)).expanduser()
            if sidecar
            else Path("~/.agents/state/cost/claude_rate_limits.json").expanduser()
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
            else Path("~/.codex/auth.json").expanduser()
        ),
        usage_url=str(usage_url) if usage_url else "https://chatgpt.com/api/codex/usage",
        max_age_seconds=int(max_age) if max_age is not None else 300,
        local_fallback=_bool_value(item.get("local_fallback"), default=False),
    )
```

In `load_cost_config()`:

```python
    claude = _mapping(providers.get("claude"), "config.cost.providers.claude")
    codex = _mapping(providers.get("codex"), "config.cost.providers.codex")
```

Add to `CostConfig(...)`:

```python
        claude=_parse_claude_provider(claude),
        codex=_parse_codex_provider(codex),
```

- [ ] **Step 4: Run config tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ConfigProviderTests -v
```

Expected: current tests pass or only future collector tests fail if already added.

- [ ] **Step 5: Commit Task 2**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/config.py
git commit -m "feat(stage8): add usage provider config"
```

## Task 3: Claude Trusted Sidecar and Estimated Fallback

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/providers.py`

- [ ] **Step 1: Write failing Claude collector tests**

Update provider imports:

```python
from paulshaclaw.cost.providers import (
    _read_local_observed_total,
    collect_all,
    collect_claude,
    collect_codex,
    collect_copilot,
)
```

Add tests in `Stage8ConfigProviderTests` after Codex stub test:

```python
    def test_collect_claude_parses_statusline_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "claude_rate_limits.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "rate_limits": {
                            "five_hour": {
                                "used_percentage": 18,
                                "resets_at": 1777466460,
                            },
                            "seven_day": {
                                "used_percentage": 41,
                                "resets_at": 1777696800,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=sidecar,
                max_age_seconds=300,
                now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.windows["five_hour"].used_percent, 18)
        self.assertEqual(provider.windows["five_hour"].display_reset, "15:21")
        self.assertEqual(provider.windows["weekly"].used_percent, 41)
        self.assertEqual(provider.windows["weekly"].display_reset, "3d")

    def test_collect_claude_unknown_when_sidecar_missing(self) -> None:
        provider = collect_claude(
            statusline_sidecar=Path("/tmp/missing-claude-rate-limits.json"),
            local_fallback=False,
        )

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})

    def test_collect_claude_estimated_fallback_excludes_gemma4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = Path(tmpdir) / ".claude" / "projects" / "p1"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-sonnet-4.5",
                                    "usage": {"input_tokens": 50, "output_tokens": 50},
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "message": {
                                    "model": "gemma4-31b-mtp",
                                    "usage": {"input_tokens": 1000, "output_tokens": 1000},
                                }
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_claude(
                statusline_sidecar=Path(tmpdir) / "missing.json",
                local_fallback=True,
                claude_home=Path(tmpdir) / ".claude",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 1)
        self.assertEqual(provider.note, "local Claude Code token estimate")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_claude_parses_statusline_sidecar \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_claude_unknown_when_sidecar_missing \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_claude_estimated_fallback_excludes_gemma4 \
  -v
```

Expected: failures because `collect_claude()` has no parameters and returns stub.

- [ ] **Step 3: Implement Claude helpers**

Edit imports in `providers.py`:

```python
import time
from datetime import datetime, timezone
```

Import `UsageWindow` and config classes:

```python
from paulshaclaw.cost.config import ClaudeProviderConfig, CodexProviderConfig, CopilotAccountConfig, CostConfig
from paulshaclaw.cost.models import CopilotAccountUsage, ProviderSnapshot, UsageWindow
```

Add helpers before `collect_codex()`:

```python
_DEFAULT_ZONE = ZoneInfo("Asia/Taipei")


def _now_utc(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _display_reset(reset_at: datetime | None, *, now: datetime | None = None) -> str | None:
    if reset_at is None:
        return None
    current = _now_utc(now)
    reset_utc = reset_at.astimezone(timezone.utc)
    delta_seconds = max(0, int((reset_utc - current).total_seconds()))
    if delta_seconds >= 48 * 3600:
        return f"{delta_seconds // 86400}d"
    if delta_seconds >= 6 * 3600:
        return f"{delta_seconds // 3600}h"
    return reset_at.astimezone(_DEFAULT_ZONE).strftime("%H:%M")


def _parse_epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _window_from_rate_limit(raw: Any, *, now: datetime | None = None) -> UsageWindow | None:
    if not isinstance(raw, Mapping):
        return None
    pct = raw.get("used_percentage", raw.get("used_percent"))
    try:
        used_percent = int(round(float(pct)))
    except (TypeError, ValueError):
        return None
    reset_at = _parse_epoch(raw.get("resets_at", raw.get("reset_at")))
    display_reset = _display_reset(reset_at, now=now)
    if display_reset is None:
        return None
    return UsageWindow(
        used_percent=max(0, min(100, used_percent)),
        reset_at=reset_at,
        display_reset=display_reset,
    )


def _read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_is_fresh(path: Path, *, max_age_seconds: int) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age_seconds
    except OSError:
        return False
```

Add local Claude fallback:

```python
def _claude_local_token_total(claude_home: Path) -> int:
    total = 0
    projects = claude_home / "projects"
    if not projects.exists():
        return 0
    for path in projects.rglob("*.jsonl"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = payload.get("message") if isinstance(payload, dict) else None
            if not isinstance(message, Mapping):
                continue
            model = str(message.get("model", "")).lower()
            if "gemma4" in model or "vllm" in model or "openai-compatible" in model:
                continue
            if not model.startswith("claude-"):
                continue
            usage = message.get("usage")
            if not isinstance(usage, Mapping):
                continue
            for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                try:
                    total += int(usage.get(key, 0) or 0)
                except (TypeError, ValueError):
                    continue
    return total


def _estimated_window_from_tokens(tokens: int) -> dict[str, UsageWindow]:
    if tokens <= 0:
        return {}
    used_percent = max(1, min(100, tokens // 10000))
    return {
        "five_hour": UsageWindow(
            used_percent=used_percent,
            reset_at=None,
            display_reset="local",
        )
    }
```

Replace `collect_claude()`:

```python
def collect_claude(
    *,
    statusline_sidecar: Path | None = None,
    max_age_seconds: int = 300,
    local_fallback: bool = False,
    claude_home: Path | None = None,
    now: datetime | None = None,
) -> ProviderSnapshot:
    sidecar = statusline_sidecar or Path("~/.agents/state/cost/claude_rate_limits.json").expanduser()
    try:
        if sidecar.exists() and _file_is_fresh(sidecar, max_age_seconds=max_age_seconds):
            payload = _read_json_file(sidecar)
            rate_limits = payload.get("rate_limits") if isinstance(payload, Mapping) else None
            if isinstance(rate_limits, Mapping):
                five_hour = _window_from_rate_limit(rate_limits.get("five_hour"), now=now)
                weekly = _window_from_rate_limit(rate_limits.get("seven_day"), now=now)
                windows = {
                    key: value
                    for key, value in (("five_hour", five_hour), ("weekly", weekly))
                    if value is not None
                }
                if windows:
                    return ProviderSnapshot(source_status="fresh", windows=windows)
    except (OSError, json.JSONDecodeError, ValueError):
        pass

    if local_fallback:
        tokens = _claude_local_token_total(claude_home or Path("~/.claude").expanduser())
        windows = _estimated_window_from_tokens(tokens)
        if windows:
            return ProviderSnapshot(
                source_status="estimated",
                windows=windows,
                note="local Claude Code token estimate",
            )

    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="credentials or trusted quota source unavailable",
    )
```

- [ ] **Step 4: Run Claude tests**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_claude_parses_statusline_sidecar \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_claude_unknown_when_sidecar_missing \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_claude_estimated_fallback_excludes_gemma4 \
  -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/providers.py
git commit -m "feat(stage8): collect Claude footer usage"
```

## Task 4: Codex Trusted Source and Estimated Fallback

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/providers.py`

- [ ] **Step 1: Write failing Codex collector tests**

Add tests in `Stage8ConfigProviderTests`:

```python
    def test_collect_codex_parses_quota_payload(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 23,
                    "reset_at": 1777466460,
                },
                "secondary_window": {
                    "used_percent": 41,
                    "reset_at": 1777696800,
                },
            }
        }

        provider = collect_codex(
            enabled=True,
            auth_path=Path("/tmp/auth.json"),
            usage_url="https://chatgpt.com/api/codex/usage",
            fetcher=lambda url, headers: payload,
            token_reader=lambda path: ("access-token", "account-id"),
            now=datetime(2026, 4, 29, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        )

        self.assertEqual(provider.source_status, "fresh")
        self.assertEqual(provider.windows["five_hour"].used_percent, 23)
        self.assertEqual(provider.windows["five_hour"].display_reset, "15:21")
        self.assertEqual(provider.windows["weekly"].used_percent, 41)
        self.assertEqual(provider.windows["weekly"].display_reset, "3d")

    def test_collect_codex_falls_back_to_estimated_local_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = Path(tmpdir) / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                json.dumps(
                    {
                        "payload": {
                            "type": "token_count",
                            "total_token_usage": {"total_tokens": 50000},
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            provider = collect_codex(
                enabled=True,
                auth_path=Path(tmpdir) / "missing-auth.json",
                local_fallback=True,
                codex_home=Path(tmpdir) / ".codex",
            )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.windows["five_hour"].used_percent, 5)
        self.assertEqual(provider.note, "local Codex token estimate")

    def test_collect_codex_unknown_when_disabled_or_no_data(self) -> None:
        provider = collect_codex(enabled=False)

        self.assertEqual(provider.source_status, "unknown")
        self.assertEqual(provider.windows, {})
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_codex_parses_quota_payload \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_codex_falls_back_to_estimated_local_tokens \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_codex_unknown_when_disabled_or_no_data \
  -v
```

Expected: failures because `collect_codex()` has no parameters and returns stub.

- [ ] **Step 3: Implement Codex helpers**

Add callables near existing type aliases:

```python
JsonFetcher = Callable[[str, Mapping[str, str]], dict[str, Any]]
CodexTokenReader = Callable[[Path], tuple[str, str]]
```

Add helper functions:

```python
def _read_codex_token(auth_path: Path) -> tuple[str, str]:
    payload = _read_json_file(auth_path)
    if not isinstance(payload, Mapping):
        raise ValueError("invalid Codex auth payload")
    access_token = payload.get("access_token")
    account_id = payload.get("account_id")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("missing Codex access token")
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("missing Codex account id")
    return access_token, account_id


def _fetch_codex_usage(url: str, headers: Mapping[str, str]) -> dict[str, Any]:
    return _fetch_json(url, headers)


def _codex_window(raw: Any, *, now: datetime | None = None) -> UsageWindow | None:
    if not isinstance(raw, Mapping):
        return None
    pct = raw.get("used_percent", raw.get("usedPercentage"))
    try:
        used_percent = int(round(float(pct)))
    except (TypeError, ValueError):
        return None
    reset_at = _parse_epoch(raw.get("reset_at", raw.get("resetsAt")))
    display_reset = _display_reset(reset_at, now=now)
    if display_reset is None:
        return None
    return UsageWindow(
        used_percent=max(0, min(100, used_percent)),
        reset_at=reset_at,
        display_reset=display_reset,
    )


def _codex_local_token_total(codex_home: Path) -> int:
    total = 0
    sessions = codex_home / "sessions"
    if not sessions.exists():
        return 0
    for path in sessions.rglob("*.jsonl"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            body = payload.get("payload") if isinstance(payload, dict) else None
            if not isinstance(body, Mapping) or body.get("type") != "token_count":
                continue
            usage = body.get("total_token_usage")
            if not isinstance(usage, Mapping):
                continue
            try:
                total = max(total, int(usage.get("total_tokens", 0) or 0))
            except (TypeError, ValueError):
                continue
    return total
```

Replace `collect_codex()`:

```python
def collect_codex(
    *,
    enabled: bool = True,
    auth_path: Path | None = None,
    usage_url: str = "https://chatgpt.com/api/codex/usage",
    local_fallback: bool = False,
    codex_home: Path | None = None,
    fetcher: JsonFetcher | None = None,
    token_reader: CodexTokenReader | None = None,
    now: datetime | None = None,
) -> ProviderSnapshot:
    if enabled:
        try:
            reader = token_reader or _read_codex_token
            access_token, account_id = reader(auth_path or Path("~/.codex/auth.json").expanduser())
            payload = (fetcher or _fetch_codex_usage)(
                usage_url,
                {
                    "Authorization": f"Bearer {access_token}",
                    "chatgpt-account-id": account_id,
                },
            )
            rate_limit = payload.get("rate_limit") if isinstance(payload, Mapping) else None
            if isinstance(rate_limit, Mapping):
                five_hour = _codex_window(rate_limit.get("primary_window"), now=now)
                weekly = _codex_window(rate_limit.get("secondary_window"), now=now)
                windows = {
                    key: value
                    for key, value in (("five_hour", five_hour), ("weekly", weekly))
                    if value is not None
                }
                if windows:
                    return ProviderSnapshot(source_status="fresh", windows=windows)
        except Exception:
            pass

    if local_fallback:
        tokens = _codex_local_token_total(codex_home or Path("~/.codex").expanduser())
        windows = _estimated_window_from_tokens(tokens)
        if windows:
            return ProviderSnapshot(
                source_status="estimated",
                windows=windows,
                note="local Codex token estimate",
            )

    return ProviderSnapshot(
        source_status="unknown",
        windows={},
        note="trusted quota windows unavailable",
    )
```

- [ ] **Step 4: Run Codex tests**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_codex_parses_quota_payload \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_codex_falls_back_to_estimated_local_tokens \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_codex_unknown_when_disabled_or_no_data \
  -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/providers.py
git commit -m "feat(stage8): collect Codex footer usage"
```

## Task 5: Copilot Month-Bounded Estimated Fallback

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/providers.py`

- [ ] **Step 1: Write failing Copilot month filter test**

Replace or extend `test_read_local_observed_total_parses_real_shutdown_event_shape` with:

```python
    def test_read_local_observed_total_counts_current_month_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / ".copilot" / "session-state" / "s1"
            root.mkdir(parents=True)
            (root / "events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session.shutdown",
                                "timestamp": "2026-04-30T23:59:00Z",
                                "data": {"totalPremiumRequests": 99},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "session.shutdown",
                                "timestamp": "2026-05-01T00:01:00Z",
                                "data": {"totalPremiumRequests": 5},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "session.shutdown",
                                "timestamp": "2026-05-20T12:00:00Z",
                                "data": {"totalPremiumRequests": 7},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("paulshaclaw.cost.providers.Path.home", return_value=Path(tmpdir)):
                total = _read_local_observed_total(year=2026, month=5)

        self.assertEqual(total, 12)

    def test_collect_copilot_marks_local_observed_provider_estimated(self) -> None:
        cfg = CostConfig(
            copilot_accounts=(
                cost_config_module.CopilotAccountConfig(
                    account_id="local-user",
                    label="local",
                    kind="personal",
                    monthly_allowance=100,
                ),
            )
        )

        def fetcher(account):
            raise RuntimeError("network unavailable")

        provider = collect_copilot(
            cfg,
            fetcher=fetcher,
            local_observed={"local-user": 12},
        )

        self.assertEqual(provider.source_status, "estimated")
        self.assertEqual(provider.accounts[0].source, "local_observed")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_read_local_observed_total_counts_current_month_only \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_copilot_marks_local_observed_provider_estimated \
  -v
```

Expected: first test fails due unsupported args; second may currently expect `stale`.

- [ ] **Step 3: Implement month filtering**

Modify `_read_local_observed_total`:

```python
def _event_month(payload: Mapping[str, Any]) -> tuple[int, int] | None:
    raw = payload.get("timestamp") or payload.get("created_at")
    if not isinstance(raw, str):
        data = payload.get("data")
        if isinstance(data, Mapping):
            raw = data.get("timestamp") or data.get("created_at")
    if not isinstance(raw, str):
        return None
    value = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.year, dt.month


def _read_local_observed_total(year: int | None = None, month: int | None = None) -> int:
    root = Path.home() / ".copilot" / "session-state"
    if not root.exists():
        return 0
    if year is None or month is None:
        year, month = _current_month_utc()
    ...
                    event_month = _event_month(payload)
                    if event_month is not None and event_month != (year, month):
                        continue
```

Keep events without timestamp for backward compatibility by counting them only when no explicit year/month args were passed:

```python
                    if event_month is None and (year is not None and month is not None):
                        continue
```

Update `_collect_local_observed_usage` to call current month:

```python
    year, month = _current_month_utc()
    total = _read_local_observed_total(year=year, month=month)
```

Change Copilot source status:

```python
    elif has_stale:
        source_status = "estimated"
```

- [ ] **Step 4: Update existing tests that expected stale**

Change these assertions in `tests/test_stage8_cost.py`:

```python
self.assertEqual(provider.source_status, "estimated")
```

for:

- `test_collect_copilot_marks_local_observed_fallback`
- `test_collect_copilot_keeps_stale_status_when_other_accounts_are_unknown`

Do not change tests where a fresh account exists; mixed fresh + local remains `fresh`.

- [ ] **Step 5: Run Copilot tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ConfigProviderTests -v
```

Expected: all config/provider tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/providers.py
git commit -m "fix(stage8): bound Copilot local usage to current month"
```

## Task 6: Wire Config into Collectors

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/providers.py`

- [ ] **Step 1: Write failing collect_all wiring test**

Add:

```python
    def test_collect_all_passes_claude_and_codex_config(self) -> None:
        cfg = CostConfig(
            claude=ClaudeProviderConfig(
                statusline_sidecar=Path("/tmp/claude.json"),
                max_age_seconds=12,
                local_fallback=True,
            ),
            codex=CodexProviderConfig(
                enabled=False,
                auth_path=Path("/tmp/codex.json"),
                usage_url="https://example.invalid/usage",
                max_age_seconds=34,
                local_fallback=True,
            ),
        )

        with (
            patch("paulshaclaw.cost.providers.collect_claude", return_value=ProviderSnapshot(source_status="unknown", windows={})) as claude,
            patch("paulshaclaw.cost.providers.collect_codex", return_value=ProviderSnapshot(source_status="unknown", windows={})) as codex,
            patch("paulshaclaw.cost.providers.collect_copilot", return_value=ProviderSnapshot(source_status="unknown", accounts=())),
        ):
            collect_all(cfg)

        claude.assert_called_once_with(
            statusline_sidecar=Path("/tmp/claude.json"),
            max_age_seconds=12,
            local_fallback=True,
        )
        codex.assert_called_once_with(
            enabled=False,
            auth_path=Path("/tmp/codex.json"),
            usage_url="https://example.invalid/usage",
            local_fallback=True,
        )
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_all_passes_claude_and_codex_config -v
```

Expected: failure because `collect_all()` calls no-arg collectors.

- [ ] **Step 3: Update `collect_all()`**

In `providers.py`:

```python
def collect_all(config: CostConfig) -> dict[str, ProviderSnapshot]:
    providers = {
        "cdx": collect_codex(
            enabled=config.codex.enabled,
            auth_path=config.codex.auth_path,
            usage_url=config.codex.usage_url,
            local_fallback=config.codex.local_fallback,
        ),
        "cc": collect_claude(
            statusline_sidecar=config.claude.statusline_sidecar,
            max_age_seconds=config.claude.max_age_seconds,
            local_fallback=config.claude.local_fallback,
        ),
    }
    copilot = collect_copilot(config)
    if copilot.accounts:
        providers["cpt"] = copilot
    return providers
```

- [ ] **Step 4: Run collect_all tests**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_all_passes_claude_and_codex_config \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_all_omits_copilot_when_no_accounts_are_configured \
  tests.test_stage8_cost.Stage8ConfigProviderTests.test_collect_all_includes_copilot_when_accounts_are_configured \
  -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/providers.py
git commit -m "feat(stage8): wire provider config into collectors"
```

## Task 7: Degraded Copilot Display and Cache Permissions

**Files:**
- Modify: `tests/test_stage8_cost.py`
- Modify: `paulshaclaw/cost/status.py`
- Modify: `paulshaclaw/cost/cache.py`

- [ ] **Step 1: Write failing degraded status test**

Add to `Stage8CliTests`:

```python
    def test_status_main_degraded_snapshot_keeps_configured_copilot_accounts(self) -> None:
        config = CostConfig(
            cache_dir=Path("/ignored"),
            cache_ttl_seconds=120,
            copilot_accounts=(
                cost_config_module.CopilotAccountConfig(
                    account_id="hamanpaul",
                    label="haman",
                    kind="personal",
                    monthly_allowance=1500,
                ),
            ),
        )
        cache = Mock()
        cache.read_if_fresh.return_value = None
        cache.read_stale.return_value = None
        lock_cm = Mock()
        lock_cm.__enter__ = Mock(return_value=False)
        lock_cm.__exit__ = Mock(return_value=False)
        cache.lock.return_value = lock_cm
        stdout = StringIO()

        with (
            patch.object(cost_status_cli, "load_cost_config", return_value=config),
            patch.object(cost_status_cli, "SnapshotCache", return_value=cache),
            patch.object(cost_status_cli, "format_footer", wraps=format_footer),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = cost_status_cli.main(["--plain"])

        self.assertEqual(exit_code, 0)
        self.assertIn("cpt haman:--", stdout.getvalue())
```

- [ ] **Step 2: Write failing cache permission test**

Add to `Stage8CacheTests`:

```python
    @unittest.skipUnless(hasattr(os, "chmod"), "POSIX permission test requires chmod")
    def test_cache_directory_is_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cost"
            cache = SnapshotCache(cache_dir, ttl_seconds=120)
            snapshot = build_snapshot(
                timezone="Asia/Taipei",
                providers={"cdx": ProviderSnapshot(source_status="unknown", windows={})},
            )

            cache.write(snapshot)

            mode = cache_dir.stat().st_mode & 0o777
            self.assertEqual(mode, 0o700)
```

Add `import os` at the top of `tests/test_stage8_cost.py`.

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python3 -m unittest \
  tests.test_stage8_cost.Stage8CliTests.test_status_main_degraded_snapshot_keeps_configured_copilot_accounts \
  tests.test_stage8_cost.Stage8CacheTests.test_cache_directory_is_owner_only \
  -v
```

Expected: degraded cpt test fails; permission test may fail with mode not `0700`.

- [ ] **Step 4: Implement degraded snapshot account preservation**

In `status.py`, import `CopilotAccountUsage`:

```python
from .models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot
```

Replace `_build_degraded_snapshot()`:

```python
def _build_degraded_snapshot(config) -> CostSnapshot:
    providers = {
        "cdx": ProviderSnapshot(source_status="unknown", windows={}),
        "cc": ProviderSnapshot(source_status="unknown", windows={}),
    }
    accounts = []
    for account in getattr(config, "copilot_accounts", ()):
        accounts.append(
            CopilotAccountUsage(
                account_id=account.account_id,
                label=account.label,
                kind=account.kind,
                used_requests=None,
                monthly_allowance=account.monthly_allowance,
                source="unknown",
            )
        )
    if accounts:
        providers["cpt"] = ProviderSnapshot(source_status="unknown", accounts=tuple(accounts))
    return build_snapshot(
        timezone=getattr(config, "timezone", "Asia/Taipei"),
        cache_status="stale",
        providers=providers,
    )
```

Update call site:

```python
else _build_degraded_snapshot(config)
```

- [ ] **Step 5: Implement cache permission hardening**

In `cache.py`, add:

```python
def _ensure_owner_only_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
```

Use it in `write()` and `lock()`:

```python
    def write(self, snapshot: CostSnapshot) -> None:
        _ensure_owner_only_dir(self.cache_dir)
        ...

    @contextmanager
    def lock(self) -> Iterator[bool]:
        _ensure_owner_only_dir(self.cache_dir)
        ...
```

- [ ] **Step 6: Run status/cache tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost.Stage8CacheTests tests.test_stage8_cost.Stage8CliTests -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add tests/test_stage8_cost.py paulshaclaw/cost/status.py paulshaclaw/cost/cache.py
git commit -m "fix(stage8): preserve degraded footer accounts"
```

## Task 8: Documentation and OpenSpec Validation

**Files:**
- Modify: `docs/superpowers/specs/2026-04-29-stage8-cost-footer-design.md`
- Verify: `openspec/changes/fix-stage8-footer-usage/*`

- [x] **Step 1: Update Stage 8 design doc wording**

In `docs/superpowers/specs/2026-04-29-stage8-cost-footer-design.md`, update sections 5.1 and 5.2:

```markdown
### 5.1 Codex (`cdx`)

Codex uses the Codex CLI quota source when available. The adapter maps the primary quota window to `five_hour` and the secondary quota window to `weekly`. Because the source is not a public OpenAI Platform API contract, failures degrade to local estimated data or `--` without interrupting the footer.

Local Codex session/token data may be shown only as `estimated` fallback with the `?` marker. It must not be presented as trusted quota usage.

### 5.2 Claude Code (`cc`)

Claude Code uses the Claude Code statusline `rate_limits` sidecar as the trusted quota source. The adapter maps `five_hour` to the 5-hour footer window and `seven_day` to the weekly footer window.

Local fallback may use Claude Code session/token data only as `estimated` fallback. It must exclude gemma4, vLLM, and OpenAI-compatible local model usage so local Claude-like model traffic is not counted as Claude Code quota.
```

- [x] **Step 2: Run full Stage 8 tests**

Run:

```bash
python3 -m unittest tests.test_stage8_cost -v
```

Expected: all tests pass.

- [x] **Step 3: Run OpenSpec status**

Run:

```bash
openspec status --change fix-stage8-footer-usage
```

Expected: all artifacts complete.

- [x] **Step 4: Inspect git status**

Run:

```bash
git --no-pager status --short --branch
```

Expected: branch `feature/stage8-footer-usage`, only intended files changed.

- [x] **Step 5: Commit docs and OpenSpec artifacts**

```bash
git add \
  docs/superpowers/specs/2026-04-29-stage8-cost-footer-design.md \
  docs/superpowers/plans/2026-05-25-fix-stage8-footer-usage.md \
  openspec/changes/fix-stage8-footer-usage
git commit -m "docs(stage8): propose footer usage fix"
```

## Self-Review

- Spec coverage: Tasks 1-7 cover estimated display, Claude sidecar, Codex quota source, Copilot local fallback, cache permissions, and degraded account visibility. Task 8 covers docs/OpenSpec validation.
- Placeholder scan: Every task includes exact files, code snippets, commands, and expected results; no unresolved markers remain.
- Type consistency: The plan consistently uses `source_status="estimated"`, `ClaudeProviderConfig`, `CodexProviderConfig`, `collect_claude(...)`, `collect_codex(...)`, and `UsageWindow`.
