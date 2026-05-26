## 1. 收納 claude-gemma4 到 repo

- [x] 1.1 複製 `~/.local/bin/claude-gemma4` 到 `scripts/claude-gemma4`，修改 `GEMMA_PROXY` 路徑為 `$REPO/scripts/claude-gemma4-proxy`
- [x] 1.2 複製 `~/.local/bin/claude-gemma4-proxy` 到 `scripts/claude-gemma4-proxy`
- [x] 1.3 從 `~/.claude-gemma4/settings.json` 建立 `config/claude-gemma4-settings.json` template
- [x] 1.4 確認 `scripts/claude-gemma4` 和 `scripts/claude-gemma4-proxy` 有執行權限且可正常啟動（smoke test）
  - 驗證紀錄：`test -x scripts/claude-gemma4`、`test -x scripts/claude-gemma4-proxy`、`python3 -m py_compile scripts/claude-gemma4-proxy`、`timeout 15s scripts/claude-gemma4 --help`；結果：exit status `0`，wrapper 成功輸出 Claude CLI help，proxy parse check 通過。
  - clean-state proxy start：因既有 `127.0.0.1:18080` listener 持續運作，為避免干擾，改以 Python `SourceFileLoader` 載入 checked-in `scripts/claude-gemma4-proxy` 並僅覆寫 `PORT=18081`，再以 `curl -fsS http://127.0.0.1:18081/health` 驗證回 `ok`；整個 bounded run 以 `timeout 10s` 包住，`wait_rc=124` 確認服務於驗證後由 timeout 自動停止。

## 2. Agent process 偵測工具

- [x] 2.1 在 `paulshaclaw/core/daemon.py` 新增 `_detect_agent_process()` 方法：掃描 tmux panes process tree，回傳 `(pane_id, pid)` 或 `None`
- [x] 2.2 為 `_detect_agent_process` 撰寫 unit test（mock tmux list-panes 和 process tree 查詢）

## 3. /agent 指令

- [x] 3.1 在 `commands.json` 新增 `/agent` 指令定義（含 Telegram menu entry）
- [x] 3.2 在 `daemon.py` 新增 `_handle_agent_command` handler，支援 `start`、`startf`、`stop`、`status` 子命令
- [x] 3.3 實作 `start`/`startf`：先 `_detect_agent_process` 確認未運行 → `tmux split-window -h` → 執行 claude-gemma4（加/不加 -f）→ 記住 `_agent_pane_id`
- [x] 3.4 實作 `stop`：先偵測 → `tmux send-keys exit Enter` → 清除 `_agent_pane_id`
- [x] 3.5 實作 `status`：`_detect_agent_process` 回傳結果 → 格式化為 "running pane=%X" 或 "stopped"
- [x] 3.6 為 `/agent` handler 四個子命令撰寫 unit test

## 4. 非指令對話路由修改

- [x] 4.1 修改 `telegram.py` 的 `TelegramCommandRouter`：移除 `chat_backend` 參數，非指令路由改為呼叫 daemon 的 agent 路由方法
- [x] 4.2 在 daemon 新增 `route_to_agent(user_id, text)` 方法：偵測 process → send-keys `[user:<user_id>] <text>` → 回傳 `"…"` 或 fallback
- [x] 4.3 修改 `listener.py`：移除 `create_chat_backend()` 呼叫和 import
- [x] 4.4 為對話路由（agent running / not running 兩條路徑）撰寫 unit test

## 5. 移除 chat backend 模組

- [x] 5.1 刪除 `paulshaclaw/chat/` 目錄（`__init__.py`、`openai.py`、`config.py`、`backend.py`）
- [x] 5.2 移除 `listener.py` 中 chat backend 專屬 wiring；保留通用 Telegram IN/OUT observability log
- [x] 5.3 移除或更新引用 `paulshaclaw.chat` 的測試檔案
- [x] 5.4 確認 legacy chat backend/config/template 測試不再引用 `OPENAI_*`；`scripts/claude-gemma4` 例外保留

## 6. Telegram 指令格式化與 menu 更新

- [x] 6.1 在 `telegram.py` 的 `_format_message` 中新增 `/agent` 回覆格式化邏輯
- [x] 6.2 確認 Telegram command menu 同步包含新的 `/agent` 指令

## 7. 整合驗證

- [x] 7.1 全量 pytest 通過（baseline 419 tests 扣除移除的 chat 測試，加上新增的 agent 測試）
  - 驗證紀錄：`PYTHONPATH=. pytest -q` → `436 passed, 5 skipped, 56 subtests passed`
- [x] 7.2 手動驗證：啟動 start.sh → `/agent start` → 送非指令文字 → 確認 claude-gemma4 收到並透過 bro 回覆 → `/agent stop`
  - 驗證紀錄：以隔離 tmux session 啟動 `scripts/start.sh`（Telegram skip），再用 `python3 -m paulshaclaw.core.daemon --config <tmp>/stage1.json --command '/agent start'` 驗證 agent pane 啟動；接著以 `PaulShiaBroDaemon.route_to_agent(user_id=1001, text='manual smoke ping')` 傳送非指令訊息，並用 `tmux capture-pane` 確認 agent pane 出現 `[user:1001] manual smoke ping`；最後 `/agent stop` 與後續 `/agent status` 回到 `stopped`。
