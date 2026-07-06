## Why

`bot/listener.py` 任一 command handler 丟未知例外會殺死整個 poll loop 且無自動重生（#196，實際發生 32h 遠端停擺）——單一指令的失敗域不應是整個 listener，違反 repo 的 fail-close／失敗域分離原則。

## What Changes

- command dispatch 外層加 broad `except Exception`：記 log + 回 Telegram 錯誤訊息（單行、不含 traceback/內部路徑）→ continue poll。
- start.sh 對 bot 進程 respawn with backoff（5s→30s→120s cap），僅涵蓋 poll loop 本體意外退出；不動其他 loop。
- 既有窄型別 except 保留於內層，語意不變。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `stage1-core-runtime`: 新增 listener 例外隔離與重生要求——handler 例外不得終止 listener；bot 進程死亡須自動重生。

## Impact

- 受影響碼：`paulshaclaw/bot/listener.py`（dispatch 外圈）、`scripts/start.sh`（respawn 函式）。
- 測試：新增 handler 例外隔離單元測試 + respawn 行為測試；既有 telegram listener 測試零回歸。
- 非目標：#195（start.sh SIGKILL 孤兒）另案。
