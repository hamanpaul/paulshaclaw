## ADDED Requirements

### Requirement: Non-command messages routed to agent pane when running
The system SHALL route Telegram non-command messages to the claude-gemma4 agent pane via `tmux send-keys` when an agent process is detected in the process tree.

#### Scenario: Message forwarded to running agent
- **WHEN** operator sends a non-command message and claude-gemma4 process is detected
- **THEN** system sends `[bro:<user_id>] <text>` to the agent pane via tmux send-keys and replies to Telegram with `"…"`

#### Scenario: Message format includes source user ID
- **WHEN** operator sends a non-command message to a running agent
- **THEN** the text sent to the agent pane MUST include the Telegram user ID in the format `[bro:<user_id>]` so claude-gemma4 can use `--source-user-id` when replying via bro skill

#### Scenario: Routed message carries an explicit reply directive
- **WHEN** operator sends a non-command message to a running agent
- **THEN** the routed text MUST append a single-line directive instructing the agent to reply via the `paulshiabro-telegram-reply` skill with `--source-user-id <user_id>`, so the small claude-gemma4 model actively triggers the reply instead of inferring intent from the tag
- **AND** the directive MUST stay on one line (no embedded newline), because `tmux send-keys` delivers the text literally before a single submitting `Enter`

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
