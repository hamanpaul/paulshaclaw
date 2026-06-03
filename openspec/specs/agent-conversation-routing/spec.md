## ADDED Requirements

### Requirement: Non-command messages routed to agent pane when running
The system SHALL route Telegram non-command messages to the claude-gemma4 agent pane via `tmux send-keys` when an agent process is detected in the process tree.

#### Scenario: Message forwarded to running agent
- **WHEN** operator sends a non-command message and claude-gemma4 process is detected
- **THEN** system sends `[bro:<user_id>] <text>` to the agent pane via tmux send-keys and replies to Telegram with `"…"`

#### Scenario: Message format includes source user ID
- **WHEN** operator sends a non-command message to a running agent
- **THEN** the text sent to the agent pane MUST include the Telegram user ID in the format `[bro:<user_id>]` so claude-gemma4 can use `--source-user-id` when replying via bro skill
- **AND** the routed message MUST stay lean (just `[bro:<user_id>] <text>`); the `[bro:<user_id>]` tag itself is the trigger, recognised by the `paulshiabro-telegram-reply` skill's description rather than an inline per-message directive

### Requirement: Fallback reply when agent is not running
The system SHALL reply with a fallback message when an operator sends a non-command message and no claude-gemma4 process is detected.

#### Scenario: Fallback when agent stopped
- **WHEN** operator sends a non-command message and no claude-gemma4 process is detected
- **THEN** system replies with "agent 未啟用，請使用 /agent start"

### Requirement: Process detection precedes pane lookup
The system SHALL first check the process tree for claude-gemma4, then derive the pane ID from the detected process. The system MUST NOT rely solely on daemon-held pane_id state for routing decisions.

#### Scenario: Routing after daemon restart
- **WHEN** daemon restarts while claude-gemma4 is running and operator sends a non-command message
- **THEN** system detects the process, finds the pane, and routes the message successfully
