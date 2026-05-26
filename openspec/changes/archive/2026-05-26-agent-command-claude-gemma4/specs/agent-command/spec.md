## ADDED Requirements

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
