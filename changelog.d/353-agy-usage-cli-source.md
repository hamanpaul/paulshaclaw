---
type: feat
scope: cost
issue: 353
---

### Added

- Stage 8 cost footer 的 agy 用量來源改讀 print-mode 唯讀 slash command（`agy -p "/usage" --output-format json`）：不起 agent turn、零 token、不讀任何 credential 檔，比 `local_fallback` 讀 `~/.gemini/antigravity-cli/state.json`（agy 1.2.0 已不存在）更可信。
- 單次呼叫耗時 2.5～4s，故以 `cost.providers.agy.refresh_seconds`（預設 300s）節流：owner-only sidecar `~/.agents/state/cost/agy_usage.json`（只存 `attempted_at`／`note`／`windows`，不存 CLI 原始輸出）。`attempted_at` 每次嘗試（成功／失敗／`cli_path` 未設且 PATH 找不到 `agy`）都更新，只用來節流；新鮮度改成每個視窗自己一份 `fetched_at`（只在該視窗這輪真的被 CLI 解析出來時更新）——回傳的 `windows` 一律是 sidecar 合併後的完整視窗，CLI 實跑輪與節流輪皆同，不再只回本輪解析到的子集，消除視窗閃爍；只有**所有現存視窗的 `fetched_at` 都在 `refresh_seconds` 內**才整份判 `fresh`，否則整份 `stale` 並保留失敗原因於 `note`。過期視窗只在 `fresh` 時才 roll-forward，`stale` 狀態下不會被歸零，避免連續失敗數小時後誤報「已重置」；已過期的 `stale` 視窗改印 `(exp)` 而非過去的時鐘時間。無舊值時落到既有 `local_fallback` 或 `unknown`。`note` 只標原因類別（timeout／nonzero／invalid-json／status-not-success／group-missing／group-unparsed／cli-missing）。讀到升級前只有單一頂層 `fetched_at` 的舊格式 sidecar 時視為每個視窗共用該時間戳，下一次實際寫入即升級為新格式。
- 新增 `group`（預設 `gemini`，可設 `3p`）依 bucket id 前綴選取 5h／weekly 視窗、`timeout_seconds`、`cli_path` 設定欄，並補上 `paulshaclaw.sample.yaml` 與 README 說明。
- formatter：`windows` 非空時 agy 比照 `cdx`／`cc` 走 `_format_window_provider`（tmux footer 與 cockpit 皆是），呈現 `agy 5h:N%(reset) wk:N%(reset)`；無視窗資料時維持原本 accounts 型 `agy N%`／`?` 呈現。
