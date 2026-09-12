---
type: feat
scope: cost
issue: 353
---

### Added

- Stage 8 cost footer 的 agy 用量來源改讀 print-mode 唯讀 slash command（`agy -p "/usage" --output-format json`）：不起 agent turn、零 token、不讀任何 credential 檔，比 `local_fallback` 讀 `~/.gemini/antigravity-cli/state.json`（agy 1.2.0 已不存在）更可信。
- 單次呼叫耗時 2.5～4s，故以 `cost.providers.agy.refresh_seconds`（預設 300s）節流：節流期內直接沿用 owner-only sidecar `~/.agents/state/cost/agy_usage.json`（只存 `fetched_at`／`windows`，不存 CLI 原始輸出）；CLI 這輪失敗時若有舊值先以 `stale` 供應，否則落到既有 `local_fallback` 或 `unknown`，`note` 只標原因類別（timeout／nonzero／invalid-json／status-not-success／group-missing）。
- 新增 `group`（預設 `gemini`，可設 `3p`）依 bucket id 前綴選取 5h／weekly 視窗、`timeout_seconds`、`cli_path` 設定欄，並補上 `paulshaclaw.sample.yaml` 與 README 說明。
- formatter：`windows` 非空時 agy 比照 `cdx`／`cc` 走 `_format_window_provider`（tmux footer 與 cockpit 皆是），呈現 `agy 5h:N%(reset) wk:N%(reset)`；無視窗資料時維持原本 accounts 型 `agy N%`／`?` 呈現。
