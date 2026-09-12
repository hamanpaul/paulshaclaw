---
type: feat
scope: cost
issue: 353
---

### Added

- Stage 8 cost footer 的 agy 用量來源改讀 print-mode 唯讀 slash command（`agy -p "/usage" --output-format json`）：不起 agent turn、零 token、不讀任何 credential 檔，比 `local_fallback` 讀 `~/.gemini/antigravity-cli/state.json`（agy 1.2.0 已不存在）更可信。
- 單次呼叫耗時 2.5～4s，故以 `cost.providers.agy.refresh_seconds`（預設 300s）節流：owner-only sidecar `~/.agents/state/cost/agy_usage.json`（只存 `attempted_at`／`fetched_at`／`note`／`windows`，不存 CLI 原始輸出）拆兩個時間戳——`attempted_at` 每次嘗試（成功／失敗）都更新，只用來節流；`fetched_at` 只在 CLI 成功取得視窗時更新，用來判斷 fresh／stale。CLI 這輪失敗（或雖成功但視窗未取得）時，若有舊值先以 `stale` 供應並保留失敗原因於 `note`；節流期內持續回報 `stale`，直到 CLI 再次成功取得視窗才轉回 `fresh`——過期視窗在 `stale` 狀態下不會被歸零，避免連續失敗數小時後誤報「已重置」。無舊值時落到既有 `local_fallback` 或 `unknown`。`note` 只標原因類別（timeout／nonzero／invalid-json／status-not-success／group-missing／group-unparsed）。
- 新增 `group`（預設 `gemini`，可設 `3p`）依 bucket id 前綴選取 5h／weekly 視窗、`timeout_seconds`、`cli_path` 設定欄，並補上 `paulshaclaw.sample.yaml` 與 README 說明。
- formatter：`windows` 非空時 agy 比照 `cdx`／`cc` 走 `_format_window_provider`（tmux footer 與 cockpit 皆是），呈現 `agy 5h:N%(reset) wk:N%(reset)`；無視窗資料時維持原本 accounts 型 `agy N%`／`?` 呈現。
