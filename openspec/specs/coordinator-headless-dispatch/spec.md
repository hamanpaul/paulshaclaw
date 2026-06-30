# coordinator-headless-dispatch Specification

## Purpose
TBD - created by archiving change persona-manager-phase-b. Update Purpose after archive.
## Requirements
### Requirement: AgentLauncher seam 與三 executor headless 啟動

系統 SHALL 提供 `AgentLauncher` Protocol seam，以 headless subprocess（**非 tmux pane**）啟動 agent，並提供 copilot / claude / codex 三個真實作。每個真實作 MUST 以 prompt 為單一 argv 元素、於指定 worktree 為 cwd、帶該家的 remote 旗標與 JSONL 輸出旗標啟動，並回傳含 `executor`、`session_name`、`pid`、`log_path` 的 handle。真實作 MUST 可經 seam 注入以便測試注入 fake（不啟動真 subprocess）。

#### Scenario: copilot headless 啟動組正確 argv

- **WHEN** 以 copilot launcher 啟動一個 slice
- **THEN** 組出的 argv 含 `-p <prompt>`（prompt 為單一元素）、`--remote`、`--name <slice_id>`、`--output-format json`，cwd 為該 worktree，且不經 `tmux send-keys`

#### Scenario: 注入 fake launcher 不啟真 subprocess

- **WHEN** 測試以 fake `AgentLauncher` 注入 dispatch 流程
- **THEN** 不啟動任何真實 subprocess，且 fake 收到正確的 `slice_id`/`prompt`/`worktree`

#### Scenario: launch 失敗為 per-slice 隔離

- **WHEN** 某 slice 的 launch 失敗（executor 不存在或 argv 錯）
- **THEN** 該 slice 不入 registry 並冒泡錯誤，不影響其他就緒單位的啟動

### Requirement: JobRegistry 記錄 session↔task 對應

`JobRegistry` SHALL 為每個 headless job 記錄 `executor`、`session_name`（= `slice_id`）、`pid`、`log_path` 與 `exit_code`，使 session 可反查 task。

#### Scenario: 啟動後 job 含 session 對應欄位

- **WHEN** headless 啟動一個 slice 後查該 job
- **THEN** job 含 `executor`、`session_name`（等於 `slice_id`）、`pid`、`log_path` 欄位

### Requirement: 完成偵測以 subprocess exit 與 JSONL result 為準

完成偵測 SHALL 以 subprocess exit code 搭配末筆 JSONL `result` 判定 job 為 `done` 或 `failed`；JSONL 不可解析時 MUST fallback 以 exit code 判定。

#### Scenario: 正常結束標 done

- **WHEN** headless subprocess 以 exit code 0 結束且末筆 JSONL 為成功 result
- **THEN** 對應 job 標為 `done`

#### Scenario: JSONL 不可解則 fallback exit code

- **WHEN** JSONL 輸出無法解析
- **THEN** 以 exit code 判定（0→done、非 0→failed），不拋例外

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

### Requirement: argv builder 與 SubprocessLauncher 支援 model passthrough

三家 argv builder（`build_copilot_argv` / `build_claude_argv` / `build_codex_argv`）SHALL 接受選用參數 `model: str | None = None`；當 `model` 非 None 時 MUST 在 argv append `--model <model>`，為 None 時 MUST NOT 加入任何 model 旗標（維持各 executor 預設）。`SubprocessLauncher.__init__` SHALL 接受 `model: str | None = None` 並於 `launch` 時傳入對應 argv builder。

#### Scenario: copilot argv 帶 model

- **WHEN** 以 `model="claude-haiku-4.5"` 呼叫 `build_copilot_argv(...)`
- **THEN** 回傳 argv MUST 含相鄰的 `--model` 與 `claude-haiku-4.5`

#### Scenario: model 未設不加旗標

- **WHEN** 不帶 `model`（None）呼叫任一 argv builder
- **THEN** 回傳 argv MUST NOT 含 `--model`

#### Scenario: SubprocessLauncher 將 model 傳入 argv builder

- **WHEN** `SubprocessLauncher(executor="copilot", model="claude-haiku-4.5")` 執行 `launch(...)`
- **THEN** 啟動的 inner argv MUST 含 `--model claude-haiku-4.5`

