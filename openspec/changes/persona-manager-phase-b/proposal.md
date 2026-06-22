## Why

Phase A 把 persona 契約接上 coordinator，但派工仍是「送進 tmux pane」的設想，且 Phase A review 指出多行 prompt 不能逕經 `send-keys -l`。brainstorm 校正：manager 自主路徑根本不該碰 pane，而應以 **headless** 方式（`copilot -p` / `claude -p` / `codex exec`）啟動 agent、帶 remote 旗標、監控 JSONL 確認進度、記 session↔task、並用三家共有的 hook 把進度 relay 回 PaulShiaBro。headless 讓多行 transport 問題消滅、完成偵測（umbrella Gap C）由 subprocess exit + JSONL 取代猜測。

## What Changes

- 新增 `paulshaclaw/coordinator/launcher.py`：`AgentLauncher` pluggable seam + **copilot / claude / codex** 三個 headless 真實作（各帶 remote、JSONL、autonomous、cwd=worktree、`--name=slice_id`）。
- 重構 Phase A `build_dispatch_command` → `build_dispatch_prompt(role, *, task, plan_path, catalog)`：產 executor-agnostic 純文字 prompt（去除 shlex/shell 包裝）。
- 擴充 `JobRegistry`：記 `executor` / `session_name(=slice_id)` / `pid` / `log_path` / `exit_code`。
- 新增完成偵測：subprocess exit code + 末筆 JSONL result（fallback exit_code）。
- 新增進度 relay：一支共用 hook script，註冊於三家**共有事件** `session_start` + `stop`，經 env `PSC_SLICE_ID` 標記、復用現有 bro-bridge 推 PaulShiaBro。
- `coordinator.autonomy.dispatch_ready`：就緒單位改由 `AgentLauncher` headless 啟動（取代 `%{i}` 佔位 + pane send）。

## Capabilities

### New Capabilities

- `coordinator-headless-dispatch`: manager 自主路徑以 headless executor（copilot/claude/codex）啟動 agent、記 session↔task、由 subprocess exit + JSONL 偵測完成、以三家共有 hook（session_start/stop）relay 進度回 PaulShiaBro。

### Modified Capabilities

- `coordinator-cli`: `dispatch_ready` 由「組佔位 command + pane send」改為「`build_dispatch_prompt` + `AgentLauncher` headless 啟動」；`build_dispatch_command` 重構為 `build_dispatch_prompt`（純文字 prompt，executor-agnostic）。

## Impact

- 代碼：新增 `paulshaclaw/coordinator/launcher.py`、relay hook script（`scripts/coordinator/psc-relay-hook.sh` + 三家 hook 註冊範本）；修改 `paulshaclaw/coordinator/{contract_command.py,autonomy.py,registry.py}`；新增/修改對應 `tests/`。
- 設計依據：`docs/superpowers/specs/2026-06-22-persona-manager-phase-b-headless-dispatch-design.md`（取代 umbrella §4.2 PaneAllocator）。
- 不動路徑 1（`core/daemon.py: route_to_agent`，bot→既有 pane）。
- 仍 shadow（無 ② gate 強擋）；不含 systemd（Phase C）。
- 待驗（不擋）：copilot/codex 的 hook 在 headless 是否 fire、各家 autonomous/remote 旗標細節 —— smoke test 核定。
