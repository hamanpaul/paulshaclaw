---
type: fix
scope: cost
---
Stage 8 cost 的 cdx（Codex）本地 quota 讀取改依 `rate_limits.*.window_minutes` 分類視窗（300→5h、10080→weekly），不再靠 `primary`／`secondary` 的槽位位置猜。實際 session 紀錄有兩種形狀：舊式 `primary=300 + secondary=10080`，以及目前主流（plan_type=prolite）的 `primary=10080 + secondary=null`；後者先前被位置對應誤標成 `5h:78%`、`wk:--`，footer 與 cockpit 同時錯（兩者共用同一份 provider snapshot）。缺 `window_minutes` 的舊紀錄維持位置對應；`window_minutes` 為未知長度時該槽跳過而非誤標。
