# stage1-core-daemon-tui-bot archive

> `/opsx:archive` 在此執行上下文不可直接使用，故建立等效歸檔文件。

## scope

- Stage 1 最小可跑版：PaulShiaBro daemon、TUI pane/task 視圖、Telegram 最小指令入口。
- Workstream 範圍：`paulshaclaw/core/`、`paulshaclaw/tui/`、`paulshaclaw/bot/`、`tests/`、workstream docs/evidence。

## 實作摘要

1. 新增 `AppConfig` / `load_config()`，支援 `--config` 與 `PSC_STAGE1_CONFIG`。
2. 新增 `PaulShiaBroDaemon`，提供 `/status` 與 `/dispatch <task>`。
3. 新增 `render_pane_task_view()`，輸出 pane/task 對照表。
4. 新增 `TelegramCommandRouter`，實作授權檢查與未知指令明確錯誤。
5. 新增 `tests/test_stage1_smoke.py`，完成 Red → Green → Refactor 的 10 個 smoke tests。
6. 補齊 `module-boundaries.md`、smoke case 清單、evidence、task/todo checkbox。

## 測試證據

- Red:
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/20260420-red-unittest.txt`
- Green / Refactor:
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/20260420-green-unittest.txt`
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/20260420-refactor-unittest.txt`
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/20260420-final-unittest.txt`
- 啟動證據：
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/20260420-daemon-status.json`
  - `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/evidence/stage1-smoke-test-cases.md`

## review 結論

- review 檔：`docs/superpowers/workstreams/stage1-core-daemon-tui-bot/review.md`
- verdict：`approve`
- 摘要：review 提出的 CLI clean error 與 config validation 問題已修正；目前符合 Stage 1 最小可跑版與當前 workstream 任務。

## 未解風險

1. 真實 coordinator transport 尚未接線，這輪只固定 dispatch 契約與測試替身。
2. `todo.md` 內 Stage 0 `opsx:ff` 固定輸出格式 blocker 仍未解除。
3. Telegram / TUI 目前是最小表面，尚未接平台 round-trip 與互動式 redraw。
