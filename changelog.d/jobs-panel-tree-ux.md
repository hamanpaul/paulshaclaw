---
type: change
---
**JOBS 面板 Tree 化**：`#global-jobs` 從 Static 換成新模組 `jobs_panel.JobsPanel(Tree)`——可 focus（綠框）、原生滾輪／橫向捲動、多 phase 群展開收合（needs_human 群預設展開並掛黃色 ↳ detail child，命令不截斷）；`build_jobs_nodes` 純函式產出節點、純文字投影 diff 去閃爍、重建後保留使用者展開狀態／cursor／scroll；共用 helpers（`status_style` 等）移駐 `jobs_panel.py`，app.py re-export 保持相容。
**行預算截斷移除**：`_JOBS_LINE_BUDGET`／「… 另 N 群未顯示」硬截斷刪除，改由 Tree 捲動承載全部群組；degraded／0 slices 走 `set_message` 單行訊息，收合語意（`j`、max_height 3）不變。
**快速鍵與 help 現代化**：App 層 up/down/enter 綁定移除，改由 focused widget 原生處理（WORK=ListView、JOBS=Tree），新增 `tab` 切換面板；footer 文案簡化，help modal 重寫為「面板」分段說明。
