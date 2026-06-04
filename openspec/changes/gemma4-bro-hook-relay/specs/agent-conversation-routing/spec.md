## MODIFIED Requirements

### Requirement: Non-command messages routed to agent pane when running
The system SHALL route Telegram non-command messages to the claude-gemma4 agent pane via `tmux send-keys` when an agent process is detected in the process tree.

#### Scenario: Message forwarded to running agent
- **WHEN** operator sends a non-command message and claude-gemma4 process is detected
- **THEN** system sends `[bro:<user_id>] <text>` to the agent pane via tmux send-keys and replies to Telegram with `"…"`

#### Scenario: Message format includes source user ID
- **WHEN** operator sends a non-command message to a running agent
- **THEN** the text sent to the agent pane MUST be the lean form `[bro:<user_id>] <text>` (no in-prompt reply directive)
- **AND** the `[bro:<user_id>]` tag MUST carry the Telegram user ID so the claude-gemma4 hooks can relay the reply with `--source-user-id`

## ADDED Requirements

### Requirement: Bro replies delivered deterministically by claude-gemma4 hooks
The system SHALL relay the final assistant reply of a `[bro:<user_id>]` turn back to that Telegram user via claude-gemma4 hooks (a `UserPromptSubmit` hook recording the source user id and a `Stop` hook sending the reply), without depending on the model invoking a skill or on an in-prompt directive. Hooks MUST never block the agent (always exit 0) and MUST log failures rather than raise.

#### Scenario: Bro turn replies to the source user
- **WHEN** a prompt arriving in the claude-gemma4 pane begins with `[bro:<user_id>]` and the turn completes
- **THEN** the turn's final assistant text is sent to that user's bound Telegram chat via `reply_bridge.py --source-user-id <user_id>`

#### Scenario: Non-bro turn is not relayed
- **WHEN** a prompt that does not begin with `[bro:<user_id>]` completes
- **THEN** no Telegram relay occurs

#### Scenario: Turn with no final assistant text
- **WHEN** a `[bro:<user_id>]` turn completes with no assistant text output (e.g. tool calls only)
- **THEN** the system sends `（已完成，無文字輸出）` to the source user

#### Scenario: Reply exceeds Telegram length limit
- **WHEN** the reply text exceeds Telegram's single-message limit (~4096 characters)
- **THEN** `reply_bridge.py` splits it into multiple messages, preferring newline boundaries, preserving order
