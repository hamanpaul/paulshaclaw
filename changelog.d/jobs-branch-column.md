---
type: fix
---
多 phase 群組列的 branch 從 name 欄移到 **trailer 欄**（#314，owner 圖示規格）：`feat/...` 串在單列與群組列同一垂直欄對齊，群組列 name 欄留白；無 branch 的群組列 trailer 退回 workflow_id（#305 的身分後備語意搬到 trailer）。`_layout_columns` 的 name 自然寬只量單列。狀態顏色僅第一欄、其後白色（#311）維持。
