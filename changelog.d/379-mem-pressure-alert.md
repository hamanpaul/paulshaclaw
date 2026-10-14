---
type: feat
scope: bot
---
Telegram bot listener 每輪 polling 會檢查主機 `MemAvailable`：低於 `PSC_MEM_ALERT_LOW_MB`（預設 3072 MB）時對已綁定 chat 推一則告警，附 RSS 用量前幾名（依程序名稱彙總）；回到 `PSC_MEM_ALERT_RECOVER_MB`（預設 4096 MB）以上才解除並送恢復通知，同一次低水位只告警一次。只做通知、不做容量治理，`PSC_MEM_ALERT_DISABLED=1` 可關閉。
