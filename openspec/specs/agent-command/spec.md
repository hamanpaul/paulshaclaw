# agent-command Specification

## Purpose
Operator `/agent` commands (start, startf, attach, detach, stop, status) that manage the control agent tmux pane (claude-gemma4, or an attached existing pane) via the PaulShiaBro Telegram daemon.
## Requirements
### Requirement: Agent start creates tmux pane and launches claude-gemma4
The system SHALL create a new tmux pane by horizontally splitting the cockpit pane (`tmux split-window -h`) and execute `claude-gemma4` in the new pane when the operator sends `/agent start`.

#### Scenario: Successful agent start
- **WHEN** operator sends `/agent start` and no claude-gemma4 process is running
- **THEN** system creates a horizontal tmux split from the cockpit pane, launches `claude-gemma4` in the new pane, and replies with the new pane ID

#### Scenario: Agent already running
- **WHEN** operator sends `/agent start` and a claude-gemma4 process is already detected
- **THEN** system replies with the existing pane ID and does not create a new pane

#### Scenario: tmux unavailable
- **WHEN** operator sends `/agent start` and tmux is not available
- **THEN** system replies with an error message indicating tmux is required

### Requirement: Agent startf launches claude-gemma4 in fast mode
The system SHALL launch `claude-gemma4 -f` (fast/bare mode) when the operator sends `/agent startf`. All other behavior is identical to `/agent start`.

#### Scenario: Successful fast-mode start
- **WHEN** operator sends `/agent startf` and no claude-gemma4 process is running
- **THEN** system creates a horizontal tmux split and launches `claude-gemma4 -f` in the new pane

### Requirement: Agent stop sends exit to the agent pane
The system SHALL send `exit` via `tmux send-keys` to the agent pane when the operator sends `/agent stop`.

#### Scenario: Successful agent stop
- **WHEN** operator sends `/agent stop` and a claude-gemma4 process is running
- **THEN** system sends `exit` + Enter to the agent pane via tmux send-keys and replies confirming stop

#### Scenario: Agent not running
- **WHEN** operator sends `/agent stop` and no claude-gemma4 process is detected
- **THEN** system replies that agent is already stopped

### Requirement: Agent status reports process state
The system SHALL check the tmux process tree for a claude-gemma4 process and report the result when the operator sends `/agent status`.

#### Scenario: Agent running
- **WHEN** operator sends `/agent status` and a claude-gemma4 process is detected
- **THEN** system replies with "running" and the pane ID

#### Scenario: Agent stopped
- **WHEN** operator sends `/agent status` and no claude-gemma4 process is detected
- **THEN** system replies with "stopped"

### Requirement: Agent attach pins an existing agent pane as the control agent
The system SHALL let the operator pin an existing tmux pane that is already running an agent (e.g. a Claude Code session) as the control agent via `/agent attach %pane`. Non-reply Telegram text MUST then route to the attached pane instead of claude-gemma4 auto-detection. A Telegram reply-to target pane (#34) MUST still take precedence over the attachment. The attachment is held in daemon memory only and MUST be re-issued after the listener restarts.

#### Scenario: Attach a pane running an agent
- **WHEN** operator sends `/agent attach %160` and pane `%160` exists with a non-shell foreground command
- **THEN** system records `%160` as the attached pane and replies `agent: attached (running)` with the pane ID

#### Scenario: Refuse to attach a shell or missing pane
- **WHEN** operator sends `/agent attach %7` and pane `%7` is missing or its foreground command is an idle shell
- **THEN** system replies with an error and MUST NOT change the attachment, so Telegram text is never typed into a shell

#### Scenario: Attached pane no longer runs an agent
- **WHEN** non-reply Telegram text arrives and the attached pane is missing or has fallen back to an idle shell
- **THEN** system MUST NOT send the text and replies with the pane ID and a hint to `/agent attach` another pane or `/agent detach`

#### Scenario: Detach restores auto-detection
- **WHEN** operator sends `/agent detach`
- **THEN** system clears the attachment, replies `agent: detached` with the previous pane ID (or `agent: already_detached`), and non-reply text routes via claude-gemma4 auto-detection again

#### Scenario: Status while attached
- **WHEN** operator sends `/agent status` while a pane is attached
- **THEN** system reports the attached pane ID and whether it still runs an agent, without process-tree auto-detection

### Requirement: Agent process detection via process tree scan
The system SHALL detect claude-gemma4 by scanning tmux pane process trees rather than relying solely on daemon-held state. This MUST allow rediscovery of agent processes after daemon restart.

#### Scenario: Process detection after daemon restart
- **WHEN** daemon restarts while a claude-gemma4 session is running in a tmux pane
- **THEN** `/agent status` still detects the running agent and reports its pane ID

### Requirement: Agent command registered in commands.json
The `/agent` command SHALL be registered in `commands.json` with Telegram menu entry and routed to a Python handler in daemon.py.

#### Scenario: Command appears in Telegram menu
- **WHEN** Telegram listener syncs command menu
- **THEN** `/agent` appears with description in Telegram's command suggestions

### Requirement: Agent 命令 argv 來源為 daemon 自有 config
`/agent start`／`/agent startf` 啟動之 agent 命令 argv MUST 由 daemon 自有 config 區段解析（沿 P2 env-path facade），MUST NOT 讀取 `paulsha_hippo.atomizer.config`（拆包後其 `resolve_command_argv` 之 `base_dir` 為 site-packages，相對路徑解析必壞）。config 中之 wrapper 路徑 MUST 為絕對路徑或 PATH 可解析之命令名；預設值維持 claude-gemma4 wrapper 之遷移後絕對位置。

#### Scenario: 拆包後 agent start 正常
- **WHEN** paulsha-hippo 以套件安裝、`paulshaclaw.memory` 已移除，操作者送出 `/agent start`
- **THEN** daemon MUST 以自有 config 解析出的 argv 建立 tmux pane 並啟動 agent，回覆新 pane ID

#### Scenario: config 缺 agent 命令
- **WHEN** daemon config 未設定 agent 命令且預設 wrapper 不存在
- **THEN** `/agent start` MUST 回覆明確錯誤（含應設定之 config 鍵名），MUST NOT 靜默 fallback 到套件內相對路徑

