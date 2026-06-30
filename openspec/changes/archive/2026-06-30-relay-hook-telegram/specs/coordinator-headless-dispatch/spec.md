## MODIFIED Requirements

### Requirement: 進度 relay 經三家共有 hook 推回 PaulShiaBro

系統 SHALL 提供一支共用 relay hook，註冊於三家 executor **共有的事件** `session_start` 與 `stop`（copilot `sessionStart`/`agentStop`、claude `SessionStart`/`Stop`、codex `session_start`/`stop`），以啟動時注入的環境變數 `PSC_SLICE_ID` 標記事件所屬 task。當 `PSC_SLICE_ID` 已設且非 `unknown` 時，relay hook 除寫 relay channel 檔外 MUST 經 `reply_bridge.py`（不帶 `--source-user-id`）broadcast 推送至已綁定 operator 的 Telegram chat；當 `PSC_SLICE_ID` 未設或為 `unknown`（互動 session）時 MUST NOT 推送 Telegram。relay／推送失敗 MUST NOT 影響 agent 執行或完成偵測（fire-and-forget，hook always exit 0）。

#### Scenario: stop 事件 relay 並推 Telegram
- **WHEN** headless agent 觸發 `stop` 事件且環境含 `PSC_SLICE_ID=<slice>`
- **THEN** relay 產出標記該 `<slice>` 的「完成」訊息，並經 `reply_bridge.py` broadcast 推往已綁定 operator 的 Telegram chat

#### Scenario: 互動 session 不推 Telegram（不 spam）
- **WHEN** relay hook 因互動 session fire，環境未設 `PSC_SLICE_ID`（或為 `unknown`）
- **THEN** 不呼叫 `reply_bridge.py`、不推送 Telegram（relay channel 檔依既有條件處理）

#### Scenario: relay／推送失敗不影響派工
- **WHEN** `reply_bridge.py` 缺檔或 Telegram 不可達導致推送失敗
- **THEN** agent 執行與完成偵測不受影響，hook 仍 exit 0，僅該則通知丟失
