---
type: fix
scope: cockpit
---
Cockpit JOBS 面板的 `recent_done` 歷史群改為預設收合並排除在 active 件數之外：群頭改標示「最近完成」、列內狀態把 `workflow-tracked`／`passed`／`done` 映射成 `已完成`、未知完成態映射成 `已結束`，且 upstream 若補送 `run_status=done|superseded` 時會直接略過這些已終結列，避免歷史紀錄把當前待處理工作數撐大。
