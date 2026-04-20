# stage1-core-daemon-tui-bot / module boundaries

## core

- 路徑：`paulshaclaw/core/`
- 責任：載入 Stage 1 JSON 設定、提供 `PaulShiaBroDaemon` 最小指令路由、轉送 coordinator dispatch。
- 對外介面：
  - `load_config(...)`
  - `PaulShiaBroDaemon.handle_command(...)`
  - `python -m paulshaclaw.core.daemon --config ... --command ...`

## tui

- 路徑：`paulshaclaw/tui/`
- 責任：將 pane / task 映射轉成可直接顯示的純文字表格。
- 對外介面：
  - `render_pane_task_view(config)`

## bot

- 路徑：`paulshaclaw/bot/`
- 責任：做 Telegram 最小指令入口與授權檢查，將 daemon 結果轉成訊息。
- 對外介面：
  - `TelegramCommandRouter.handle_message(...)`

## 邊界約束

1. `bot` 不直接碰 coordinator，只透過 `core` 的 daemon 指令面。
2. `tui` 只讀設定與狀態，不負責 dispatch 或授權判斷。
3. Stage 3 後續只 consume Stage 1 的 dispatch/status 入口，不直接改本次啟動流程契約。
