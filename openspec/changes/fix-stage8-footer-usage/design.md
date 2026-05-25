## Context

Stage 8 已提供 `python -m paulshaclaw.cost --once` 與 `python -m paulshaclaw.cost.status`，並用 `CostSnapshot` / `ProviderSnapshot` / `UsageWindow` 表示 provider-neutral usage。formatter 已經能呈現 `cdx` / `cc` 的 `five_hour`、`weekly` windows 與 `cpt` 的多帳號 request count；目前缺口集中在 collector 與 degraded/fallback 行為。

現況限制：

- `collect_codex()` 與 `collect_claude()` 仍為 permanent stub，永遠回 `source_status="unknown"`、`windows={}`。
- Copilot 已有 GitHub billing API primary source，但 local observed fallback 目前沒有明確月份邊界，degraded/fallback path 也可能讓已設定的 `cpt` accounts 消失。
- Claude Code 的可靠 quota source 是 statusline `rate_limits` payload；本地 gemma4/vLLM/OpenAI-compatible 使用量不是 Claude Code quota，必須排除。
- Codex 的 quota endpoint 來自 Codex CLI 使用的 ChatGPT internal API，不是 public contract；必須 best-effort 且 failure-safe。
- tmux status command 必須保持快速、單行、exit 0 degraded behavior，不能因 provider API 失敗阻塞或噴出 secrets。

## Goals / Non-Goals

**Goals:**

- 讓 `cc`、`cdx`、`cpt` 都能在可信來源可用時顯示真實 usage。
- 在可信來源不可用但 local token/session fallback 可用時，以 `estimated` 狀態與紫色 `?` 標記顯示推估值。
- 下一次可信來源成功時自動覆蓋 estimated snapshot，footer 回到正常 provider 標記。
- Claude local fallback 必須排除 gemma4/vLLM/OpenAI-compatible 地端模型用量。
- Copilot local observed fallback 僅計目前月份，並保持 account order/config-driven 行為。
- 強化 cost cache/state 目錄權限為 owner-only。
- 以既有 Stage 8 unittest 驅動實作。

**Non-Goals:**

- 不新增 daemon、server、tmux plugin 或全域 `.tmux.conf` 修改。
- 不把 Claude/Codex local token/session count 當成可信 quota；只能以 estimated 標記呈現。
- 不實作 Codex token refresh flow；token 缺失或過期時降級。
- 不將地端 gemma4/vLLM/OpenAI-compatible 呼叫納入 Claude Code usage。
- 不改變 `python -m paulshaclaw.cost --once` 與 `python -m paulshaclaw.cost.status` 的 CLI 介面。

## Decisions

### 1. Preserve the existing snapshot/formatter boundary, but extend source status

`ProviderSnapshot.source_status` 目前是 string，因此可以 backward-compatibly 支援新值 `estimated`。formatter 需要小幅擴充：

- `fresh`: provider label 不加 suffix。
- `stale`: provider label 加 `~`。
- `estimated`: provider label 加 `?`，並使用 estimated 專用紫色樣式。
- `unknown`: 顯示 `--` 或 `account:--`。

這比新增 parallel data model 更小，也讓 snapshot JSON 對 Stage 11 cockpit 保持容易理解。

### 2. Use trusted provider sources first, local estimation only as fallback

每個 provider 的 collector 採用相同策略：

1. 嘗試可信來源。
2. 可信來源成功時回 `fresh` 並填入真實 values。
3. 可信來源失敗時才嘗試 local fallback。
4. local fallback 成功時回 `estimated`，footer 使用 `?` 與紫色。
5. local fallback 也失敗時回 `unknown`。

這符合 operator UX：有數字時也能看出它是 trusted 還是 estimated。

### 3. Claude reads statusline sidecar; local fallback excludes local model traffic

Claude trusted source 是 Claude Code statusline sidecar。sidecar 由使用者在 Claude Code statusline command 或 wrapper 中寫入 agent state，例如 `~/.agents/state/cost/claude_rate_limits.json`。collector 只讀 rate limit percentage/reset，不讀 Claude API key，也不讀 local gemma4/vLLM/OpenAI-compatible chat logs。

若 statusline sidecar 不存在或過舊，Claude local fallback 只能讀 Claude Code 官方 session/transcript 來源中的 token/session 訊號，且必須以 allowlist/shape guard 排除本地 OpenAI-compatible 模型與 `gemma4-31b-mtp`。fallback 不得產生可信 quota reset，只能產生 estimated status。

### 4. Codex uses internal quota endpoint best-effort; local sessions are estimated only

Codex trusted source 是 Codex CLI ChatGPT quota endpoint。collector 讀取可用的 Codex auth metadata，呼叫 `/api/codex/usage`，將 `primary_window` 映射到 `five_hour`、`secondary_window` 映射到 `weekly`。任何 auth、timeout、schema 或 response error 都不得中斷 snapshot；改走 local session/token_count fallback 或 unknown。

Codex local session/token_count fallback 只能標 `estimated`，不能偽裝成 quota API result。

### 5. Copilot keeps GitHub billing API primary, but local observed becomes month-bounded estimated fallback

Copilot 仍以 GitHub billing `premium_request/usage` 為 primary source。API 失敗時，local observed fallback 只統計目前月份事件，並標示 `local_observed` / `estimated`，避免跨月累加。若沒有 local observed，仍顯示 configured account label with `--`。

### 6. Cache/state security is part of the fix

Snapshot 會包含 account id、labels、usage numbers 與 source status。雖然不含 token，但仍是 operator usage data。`SnapshotCache.write()` 與 `lock()` 建立 `cache_dir` 時應使用 `0700` 並修正既有寬鬆權限，避免其他本機 user 讀取。

## Risks / Trade-offs

- Codex internal endpoint 不穩定或 schema 變動 → 以 strict parser、短 timeout、failure-to-unknown/estimated 降低風險。
- Claude statusline sidecar 需要使用者環境配合 → config 預設可用但 missing 時安全降級；文件說明 wrapper/sidecar 設定。
- Estimated 數字可能被誤讀為真 quota → `?` suffix 與紫色樣式強制區分。
- Local fallback 解析不同版本 transcript 可能脆弱 → fallback 僅作 estimated，且測試涵蓋 malformed/unknown input。
- Cache permission 測試在非 POSIX 平台可能不穩 → repo 主要 Linux 環境可測；測試可在缺少 chmod 語意時跳過或聚焦 Linux。

## Migration Plan

1. 先以 TDD 新增/更新 Stage 8 tests，覆蓋 `estimated` rendering、Claude/Codex trusted/fallback/unknown、Copilot month-bounded fallback、degraded `cpt label:--`、cache permissions。
2. 實作 formatter/config/provider/cache/status 小範圍變更。
3. 執行 `python3 -m unittest tests.test_stage8_cost -v`。
4. 更新 Stage 8 docs/spec 中對 Claude/Codex stub 的描述。
5. 若部署後 Codex endpoint 不可用，透過 config disable Codex trusted source，保留 local estimated 或 unknown display。

## Open Questions

- Claude statusline sidecar 的最終 JSON 欄位是否使用原始 statusline payload 包裝，或先正規化成 repo 自有 sidecar schema？建議實作同時接受兩者，以降低環境耦合。
- Codex auth 若使用 keyring 而非 `~/.codex/auth.json`，Phase 1 是否只回 unknown/estimated？建議 Phase 1 不做 keyring 整合。
