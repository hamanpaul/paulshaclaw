---
type: feat
issue: 275
---
bro-queue 積壓超時主動回 Telegram 告警（#275，#88 follow-up）：

- `paulshaclaw/core/bro_queue.py` 新增唯讀 API `list_backlogs()` 與 `PaneBacklog`：逐一列舉 `bro-queue/` 下各 pane 佇列檔，取跨程序鎖讀內容，算出最前筆 `pending_seconds`，不改動任何佇列檔、不呼叫 `flush()`。
- 新增 `paulshaclaw/core/bro_queue_alert.py`：`BroQueueAlerter.check_and_alert()` 做門檻判斷、去重與告警文字組裝。門檻由 `PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS` 設定，預設 600 秒（10 分鐘）；以佇列最前筆 `(pane_id, queued_at)` 為去重識別，同一筆積壓只告警一次，佇列前進或清空後自動重置，新最前筆累積超過門檻才會再告警。讀佇列、送出、查綁定的例外一律吞掉 + log，絕不中斷 listener。
- `paulshaclaw/bot/listener.py` 的 polling 迴圈只掛一個 `_check_queue_backlog()` 呼叫（在 `run_once()` 末段），邏輯全在模組裡；`build_listener()` 組裝 alerter 並注入。`process_update` / `send_message` / `_safe_send` 未動。不新增常駐進程。

取捨：門檻預設 10 分鐘（長回合中不易誤觸發）；同一筆積壓不重複告警、不做「每 M 分鐘再提醒」（預設不要吵，需要時再擴）。