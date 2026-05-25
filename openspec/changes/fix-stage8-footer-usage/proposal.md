## Why

Stage 8 的 tmux footer 已經具備 provider-neutral snapshot 與 rendering 架構，但目前 Claude Code (`cc`) 與 Codex (`cdx`) collector 仍停留在 `unknown` stub，Copilot (`cpt`) 在部分 degraded / fallback 路徑也可能顯示不完整或使用跨月本機觀測值。這會讓 footer 無法可靠呈現三家 agent 的實際或可識別推估用量，降低 operator 對 quota / premium request 狀態的判斷能力。

這次變更要依最新研究結果補齊三家 provider 的可信 quota 來源，並允許在可信來源不可用時以醒目的 estimated 標記顯示 local token/session 推估值；同時明確排除 Claude 本地 gemma4/vLLM/OpenAI-compatible 模型用量，避免把地端模型誤算進 Claude Code quota。

## What Changes

- 新增 Claude Code 用量來源：優先讀 Claude Code statusline `rate_limits` sidecar，將 `five_hour` 與 `seven_day` 映射到 footer 的 `five_hour` / `weekly` windows。
- 新增 Codex 用量來源：best-effort 讀 Codex CLI ChatGPT quota endpoint (`/api/codex/usage`) 的 primary / secondary windows，失敗時安全降級。
- 保留並補強 Copilot GitHub billing `premium_request/usage` primary source，修正 local observed fallback 的月份邊界與 degraded 顯示。
- 新增 `estimated` source status 與 footer `?` 標記，使用紫色樣式區分 local token/session 推估值與可信 quota 值。
- 允許 Claude/Codex/Copilot 在可信來源不可用時才使用 local fallback；下一次可信來源成功時必須覆蓋 estimated 值。
- 明確禁止 Claude local fallback 納入本地 gemma4/vLLM/OpenAI-compatible 模型用量。
- 強化 cost cache/state 目錄權限，避免 snapshot 中的 account usage 資訊被其他本機使用者讀取。

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `stage8-cost-footer`: Stage 8 footer 將支援 Claude/Codex 可信 quota 來源、estimated fallback 標記、Copilot fallback 正確性，以及 cache/state 權限強化。

## Impact

- Affected code:
  - `paulshaclaw/cost/providers.py`
  - `paulshaclaw/cost/config.py`
  - `paulshaclaw/cost/formatter.py`
  - `paulshaclaw/cost/status.py`
  - `paulshaclaw/cost/cache.py`
  - `tests/test_stage8_cost.py`
- Affected artifacts:
  - `openspec/specs/stage8-cost-footer/spec.md`
  - Stage 8 design / docs notes if they still describe Claude/Codex as pure stubs.
- External interfaces:
  - Optional Claude statusline sidecar path under the agent state tree.
  - Optional Codex auth/usage endpoint reader, best-effort and failure-safe.
  - Existing GitHub `gh auth token` / billing API path for Copilot remains primary.
- No breaking CLI changes: `python -m paulshaclaw.cost --once` and `python -m paulshaclaw.cost.status` keep their current commands and degraded exit behavior.
