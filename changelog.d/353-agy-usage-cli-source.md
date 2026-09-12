---
type: feat
scope: cost
issue: 353
---

### Added

- Stage 8 cost footer 的 agy 用量來源改讀 print-mode 唯讀 slash command（`agy -p "/usage" --output-format json`）：不起 agent turn、零 token、不讀任何 credential 檔，比 `local_fallback` 讀 `~/.gemini/antigravity-cli/state.json`（agy 1.2.0 已不存在）更可信。
- 單次呼叫耗時 2.5～4s，故以 `cost.providers.agy.refresh_seconds`（預設 300s）節流：owner-only sidecar `~/.agents/state/cost/agy_usage.json`（只存 `attempted_at`／`fetched_at`／`note`／`windows`，不存 CLI 原始輸出；`windows` 只存 CLI 的原始解析值，絕不在寫入前 roll-forward）。一輪只有兩種結果：兩個視窗都解析成功 → 整塊替換 `windows`／`fetched_at`＝now／`note`＝null；其餘任何情況（timeout／nonzero／invalid-json／status-not-success／group-missing／window-unparsed／cli-missing，PATH 上找不到 `agy` 也算一次失敗嘗試）→ 只更新 `attempted_at`／`note`，`windows`／`fetched_at` 原樣不動——不再 merge、不再有 per-window `fetched_at`（收斂第三輪逐視窗新鮮度設計，減少活動零件）。`attempted_at` 只決定要不要節流；`fresh`／`stale` 只看 `fetched_at` 是否落在 `refresh_seconds` 內。過期視窗只在 `fresh` 時才於呈現層 roll-forward（不影響 sidecar 內容），避免連續失敗數小時後誤報「已重置」；`stale` 的過期視窗改印 `(exp)` 而非過去的時鐘時間或假造的 `0%`。新增 `stale_max_age_seconds`（預設 3600）：`fetched_at` 比它更舊時該輪不輸出視窗（sidecar 檔仍保留），落到既有 `local_fallback` 或 `unknown`，`note` 保留最後失敗原因。讀到升級前的舊格式 sidecar（第三輪的 per-window `fetched_at`，或更早只有單一頂層 `fetched_at` 的版本）不會炸：取可得的最舊 `fetched_at`（或視為無 `fetched_at`），下一次實際寫入即升級為現行格式。
- 新增 `group`（預設 `gemini`，可設 `3p`）依 bucket id 前綴選取 5h／weekly 視窗、`timeout_seconds`、`cli_path`、`stale_max_age_seconds` 設定欄，並補上 `paulshaclaw.sample.yaml` 與 README 說明。
- formatter：`windows` 非空時 agy 比照 `cdx`／`cc` 走 `_format_window_provider`（tmux footer 與 cockpit 皆是），呈現 `agy 5h:N%(reset) wk:N%(reset)`；無視窗資料時維持原本 accounts 型 `agy N%`／`?` 呈現。
