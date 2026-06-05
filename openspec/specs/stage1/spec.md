# stage1 Specification

## Purpose
Stage 1 Telegram command router handling of non-command messages: route them to the claude-gemma4 agent pane (replacing the former HTTP chat backend).

## Requirements
### Requirement: TelegramCommandRouter handles non-command messages
The TelegramCommandRouter SHALL route non-command messages through agent pane detection and tmux send-keys instead of invoking a ChatBackend. When no agent is running, it SHALL return a fallback message. The `chat_backend` constructor parameter is removed.

#### Scenario: Non-command message with agent running
- **WHEN** an authorized user sends a non-command message and claude-gemma4 process is detected
- **THEN** router sends the message to the agent pane and returns a short acknowledgment

#### Scenario: Non-command message without agent
- **WHEN** an authorized user sends a non-command message and no claude-gemma4 process is detected
- **THEN** router returns fallback message "agent 未啟用，請使用 /agent start"
