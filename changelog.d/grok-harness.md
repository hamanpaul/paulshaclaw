---
type: feat
---
- footer 與 cockpit 新增 grok 週池：只讀本機 unified log 的 `creditUsagePercent`（已是百分比），段面為 `grok wk:N%(reset)`，不印 5h；逾時仍顯示數字並標 `grok~`。`--footer` 與 install TUI 可開關，省略 yaml 時預設啟用。
- `custom-skills/add-new-harness/`：把新 harness 接進用量監控時要對齊的契約（週池 formatter、footer 選擇、測試不得讀本機活日誌）。
