# Stage 8 Cost Footer — Design

- Date: 2026-04-29
- Status: proposed
- Owner: @hamanpaul
- Topic: Stage 8 cost visibility via tmux footer and JSON snapshot CLI

## 0. 背景

Stage 8 原本在總覽中標為 postponed，主題是成本治理（token / premium budget）。這次先啟動最小可視版本：不做完整治理、不阻擋行為，只把 Codex / Claude Code / GitHub Copilot 的用量做成可掃描的 tmux footer，並提供同一份 JSON snapshot 給測試與未來 Stage 11 cockpit 消費。

外部參考的共通模式是「狀態列只做短輸出，資料收集與快取分離」。`agent-status-tmux` 顯示 Claude/Gemini 狀態並用 cache 餵 tmux；`tmux-ccusage` 用 tmux format/string 顯示 Claude cost；`claude-usage` gist 顯示 5h/7d quota、stale marker、顏色門檻與 cache。Stage 8 採用這些模式，但不直接修改全域 `~/.tmux.conf`，也不把 provider credential 暴露到 process list 或輸出。

GitHub Copilot 需要特別處理：Copilot premium request 可能由本機外的 IDE、GitHub Web、cloud agent 或其他機器消耗。本機 `~/.copilot/session-state` 只能代表本機觀測值，不能代表 account 真實用量。Stage 8 的 Copilot adapter 必須優先讀 GitHub account/org/enterprise billing 或 usage reports；本機 log 只能作為 fallback/debug signal。

GitHub 文件也標示 Copilot billing 會在 2026-06-01 從 request-based billing 轉向 usage-based billing。Stage 8 v1 仍以目前可見的 premium request 用量為主，但 provider adapter 需要把「metric 名稱」與「footer 呈現」隔離，讓後續 billing metric 變動時不需要重寫 tmux formatter。

## 1. 目標與非目標

### 1.1 目標

- 提供 `python -m paulshaclaw.cost --once`，輸出 provider-neutral JSON snapshot。
- 提供 tmux footer status command，輸出單行、可著色、低延遲的 cost summary。
- `scripts/start.sh` 在目前 tmux session 套用 Stage 8 footer，使用 session-local tmux option，不修改全域 `~/.tmux.conf`。
- 支援 `cdx`、`cc`、`cpt` 三個 provider 縮寫。
- Copilot accounts 完全由 config 宣告；sample 可包含 `hamanpaul -> haman`、`org-a -> arc`，runtime 不 hardcode 這些帳號。
- 以 hybrid source 設計 provider adapter：線上來源優先，本機 cache/log 作為 fallback。
- 缺 credential、來源錯誤或 cache stale 時，footer 仍 exit 0 並顯示 `--` 或 stale marker。

### 1.2 非目標

- 不做背景 service、socket server 或 daemon。
- 不做 cost prediction、自動限流、budget enforcement 或高風險 action gate。
- 不修改 `~/.tmux.conf`、不安裝 tmux plugin、不要求全域 tmux reload。
- Copilot v1 footer 不顯示 reset time、不顯示 max allowance；只顯示 used request count。
- 不把本機 Copilot log 當成 account quota truth。

## 2. 方案決策

| 議題 | 決策 | 理由 |
|---|---|---|
| 架構 | Snapshot CLI + footer formatter | 可測、可被 Stage 11 reuse，又比常駐 service 輕 |
| tmux 整合 | `scripts/start.sh` 套用 session-local `status-right` / `status-interval`（依 `tmux_refresh_seconds`，預設 30） | 跟現有 Stage 9/11 啟動模型一致，不碰全域設定 |
| refresh 節奏 | tmux 依 `tmux_refresh_seconds` 刷新（預設 30 秒）；snapshot cache TTL 120 秒 | 降低 provider 查詢與檔案掃描成本 |
| footer 密度 | Balanced 單行 | provider 名稱清楚，仍適合狀態列 |
| provider 縮寫 | `cdx` = Codex, `cc` = Claude Code, `cpt` = GitHub Copilot | 短、穩定、易掃描 |
| Copilot account | Config-driven 0/1/N accounts | 上線環境可能不是 `hamanpaul` / `org-a` |
| Copilot reset | v1 預留欄位但不抓、不顯示 | 降低初版資料來源風險 |
| 顏色 | 低於 70% 綠，70-89% 黃，90% 以上紅 | 讓 footer 一眼顯示風險 |

## 3. 資料模型

Stage 8 snapshot 是 provider-neutral JSON。Python 實作可用 dataclass，JSON 欄位保持穩定。

```json
{
  "generated_at": "2026-04-29T15:00:00+08:00",
  "timezone": "Asia/Taipei",
  "cache_status": "fresh",
  "providers": {
    "cdx": {
      "source_status": "fresh",
      "windows": {
        "five_hour": {
          "used_percent": 18,
          "reset_at": "2026-04-29T15:21:00+08:00",
          "display_reset": "15:21"
        },
        "weekly": {
          "used_percent": 41,
          "reset_at": "2026-05-02T10:00:00+08:00",
          "display_reset": "3d"
        }
      }
    },
    "cc": {
      "source_status": "unknown",
      "windows": {
        "five_hour": null,
        "weekly": null
      }
    },
    "cpt": {
      "source_status": "fresh",
      "accounts": [
        {
          "id": "hamanpaul",
          "label": "haman",
          "kind": "personal",
          "used_requests": 724,
          "monthly_allowance": 1500,
          "source": "github_user_billing"
        },
        {
          "id": "org-a",
          "label": "arc",
          "kind": "company",
          "used_requests": 127,
          "monthly_allowance": 300,
          "source": "github_org_or_enterprise_billing"
        }
      ]
    }
  }
}
```

Allowed status values:

- `source_status`: `fresh`, `stale`, `estimated`, `unknown`, `error`
- `source`: `github_user_billing`, `github_org_billing`, `github_enterprise_billing`, `github_premium_request_report`, `github_metrics`, `local_observed`, `unknown`

## 4. Config

Stage 8 reads config from the paulshaclaw config chain. The exact file path can follow the existing config pattern during implementation; the schema must support this shape:

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
        - id: org-a
          label: arc
          kind: company
          monthly_allowance: 300
          org: example-org
```

Runtime rules:

- `accounts: []`: omit the `cpt` footer segment.
- One account: `cpt haman:724`.
- Multiple accounts: preserve config order, e.g. `cpt haman:724 arc:127`.
- `label` is the footer label; `id` is the provider account identifier.
- `monthly_allowance` is used only for color threshold calculation and is not shown in footer.
- If the operator sees `ha` / `haman` / `arc`, that text comes from `cost.providers.copilot.accounts[].label`.

## 5. Provider Adapters

### 5.1 Codex (`cdx`)

Codex uses the Codex CLI quota source when available. The adapter maps the primary quota window to `five_hour` and the secondary quota window to `weekly`. Because the source is not a public OpenAI Platform API contract, failures degrade to local estimated data or `--` without interrupting the footer.

Local Codex session/token data may be shown only as `estimated` fallback with the `?` marker. It must not be presented as trusted quota usage.

No extra paulshaclaw-specific feature flag is required beyond `cost.providers.codex.enabled` (default `true`). If the current Codex CLI login cannot access the ChatGPT Codex usage endpoint, Stage 8 degrades to estimated local data or `--`.

### 5.2 Claude Code (`cc`)

Claude Code uses the Claude Code statusline `rate_limits` sidecar as the trusted quota source. The adapter maps `five_hour` to the 5-hour footer window and `seven_day` to the weekly footer window.

Local fallback may use Claude Code session/token data only as `estimated` fallback. It must exclude gemma4, vLLM, and OpenAI-compatible local model usage so local Claude-like model traffic is not counted as Claude Code quota.

Operationally, the sidecar is a local JSON file (default `~/.agents/state/cost/claude_rate_limits.json`) written by the operator's Claude Code statusline helper. The expected shape is:

```json
{
  "rate_limits": {
    "five_hour": { "used_percentage": 18, "resets_at": 1777447260 },
    "seven_day": { "used_percentage": 41, "resets_at": 1777696800 }
  }
}
```

Stage 8 displays `weekly` as `wk`, even if an upstream source calls it `7d`.

### 5.3 GitHub Copilot (`cpt`)

Copilot adapter source priority depends on account kind:

- `personal`: GitHub user billing premium request usage report, then configured premium request analytics/export report, then local observed logs.
- `company`: GitHub organization or enterprise billing premium request usage report, then configured org/enterprise analytics/export report, then local observed logs.

Local observed logs are explicitly incomplete because usage may happen outside this host. If an account falls back to local logs, snapshot must set `source: local_observed` so detail views can warn that the number is partial.

GitHub official docs note that user endpoints only include Copilot usage billed directly to an individual user; organization or enterprise-managed licenses require org/enterprise endpoints. Premium request counters reset monthly at 00:00:00 UTC, but Stage 8 v1 does not fetch or display Copilot reset time.

The Copilot usage metrics API is useful for activity analysis, but premium request billing usage is the preferred source for the footer count. If a future provider uses usage metrics, it must document how that metric maps to request count or expose a different metric name in the snapshot.

## 6. CLI / Cache / Tmux

### 6.1 CLI

```text
python -m paulshaclaw.cost --once
```

Outputs full JSON snapshot to stdout. It may refresh provider sources, subject to cache TTL.

```text
python -m paulshaclaw.cost.status
```

Outputs a single tmux status string and exits 0 whenever possible. It reads cache first; if cache is stale it may trigger a bounded refresh. Provider errors degrade that provider only.

### 6.2 Cache paths

```text
~/.agents/state/cost/snapshot.json
~/.agents/state/cost/snapshot.lock
~/.agents/log/cost.log
```

Rules:

- Cache TTL default is 120 seconds.
- If lock is busy, read old cache.
- If refresh fails and old cache exists, mark provider or snapshot stale.
- If no cache exists, render unknown values.
- Never write secrets to snapshot or logs.

### 6.3 Tmux startup

`scripts/start.sh` should apply Stage 8 before launching Stage 11 cockpit:

```text
tmux set-option status-interval <tmux_refresh_seconds|default 30>
tmux set-option status-right "<existing-right> #(python -m paulshaclaw.cost.status)"
```

Implementation must use session-local options and avoid global `-g`. If an existing `status-right` is present, Stage 8 appends or wraps it rather than replacing it blindly.

## 7. Footer Format

Normal format:

```text
cdx 5h:18%(15:21) wk:41%(3d)  cc 5h:-- wk:--  cpt haman:724 arc:127
```

Stale / narrow example:

```text
cdx~ 5h:18%(15:21) wk:41%(3d)  cpt haman:724
```

Rules:

- `cdx` / `cc`: `5h` reset uses configured timezone and displays `HH:MM`.
- `cdx` / `cc`: `wk` reset uses relative display, e.g. `3d`.
- `--`: no trusted data.
- `~`: provider segment is showing stale cache.
- `cpt`: displays configured account labels and used request count only.
- Color is applied by segment using tmux style syntax.

Color thresholds:

- `< 70%`: green
- `70-89%`: yellow
- `>= 90%`: red
- `unknown` / `error`: dim or neutral

For Copilot, percent is computed as `used_requests / monthly_allowance * 100`, but footer still displays only `used_requests`.

## 8. Error Handling

- Provider failure must not fail the whole footer.
- Missing credential yields `unknown`, not an exception visible in tmux.
- Malformed provider response is logged with source name and status, without response body if it may contain sensitive data.
- Network timeout must be bounded.
- Timezone parse failure falls back to `Asia/Taipei` and logs a config error.
- Config account without `label` uses `id`; without `monthly_allowance` gets no color threshold and uses neutral style.
- `python -m paulshaclaw.cost.status` should exit 0 for display fallback cases and nonzero only for programmer/config errors that prevent any output.

## 9. Tests

### 9.1 Unit tests

- Snapshot schema serialization.
- Config parsing for 0/1/N Copilot accounts.
- Copilot account labels are config-driven and sample names are not hardcoded.
- Footer formatter for normal, stale, unknown, and narrow cases.
- Color thresholds at 69, 70, 89, 90 percent.
- 5h reset display uses configured timezone and `HH:MM`.
- Weekly reset display uses relative format.
- Copilot local-observed source is marked partial/fallback.

### 9.2 Cache tests

- Fresh cache under 120 seconds is reused.
- Stale cache triggers refresh.
- Lock busy reads old cache.
- Refresh failure preserves old cache and marks stale.
- Cache/log output does not include token-like values.

### 9.3 CLI contract tests

- `python -m paulshaclaw.cost --once` prints valid JSON.
- `python -m paulshaclaw.cost.status` prints one line.
- Missing credentials still exits 0 with unknown output.
- Provider-specific error does not remove other provider segments.

### 9.4 Tmux/start tests

- `scripts/start.sh` applies the configured `status-interval` (default `30`).
- `scripts/start.sh` appends Stage 8 footer to session-local `status-right`.
- Existing `status-right` is preserved.
- No test writes or requires `~/.tmux.conf`.

### 9.5 Manual smoke

- Start inside tmux with `scripts/start.sh`.
- Confirm footer refreshes every 30 seconds.
- Confirm Stage 11 cockpit still starts.
- Confirm `cpt` displays only configured account labels and request counts.

## 10. References

- GitHub Docs — Monitoring Copilot usage and entitlements: https://docs.github.com/copilot/managing-copilot/monitoring-usage-and-entitlements/monitoring-your-copilot-usage-and-entitlements
- GitHub Docs — Billing usage REST API: https://docs.github.com/en/rest/billing/usage
- GitHub Docs — Copilot usage metrics fields and API/export data: https://docs.github.com/en/copilot/reference/copilot-usage-metrics/copilot-usage-metrics
- GitHub Docs — Copilot premium requests: https://docs.github.com/en/billing/concepts/product-billing/github-copilot-premium-requests
- `agent-status-tmux`: https://github.com/jimmyliao/agent-status-tmux
- `tmux-ccusage`: https://github.com/recca0120/tmux-ccusage
- `claude-usage` gist: https://gist.github.com/simoninglis/b6f909ba0aa2f67af872866e2f22dbd4
