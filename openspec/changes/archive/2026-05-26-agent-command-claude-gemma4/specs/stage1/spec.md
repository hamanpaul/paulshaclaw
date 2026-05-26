## REMOVED Requirements

### Requirement: OpenAI-compatible chat backend
**Reason**: Replaced by claude-gemma4 agent pane routing. The stateless HTTP chat backend is superseded by an interactive Claude Code session with context memory.
**Migration**: Non-command messages now route to the claude-gemma4 tmux pane. The `paulshaclaw/chat/` module (openai.py, config.py, backend.py) is deleted. `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` environment variables are no longer needed.

### Requirement: Chat backend conversation logging
**Reason**: The IN/OUT logging tied to the chat backend reply cycle is removed. claude-gemma4 has its own session logs.
**Migration**: Remove chat-specific IN/OUT log lines from listener.py. Standard Telegram message receipt logging remains.

## MODIFIED Requirements

### Requirement: TelegramCommandRouter handles non-command messages
The TelegramCommandRouter SHALL route non-command messages through agent pane detection and tmux send-keys instead of invoking a ChatBackend. When no agent is running, it SHALL return a fallback message. The `chat_backend` constructor parameter is removed.

#### Scenario: Non-command message with agent running
- **WHEN** an authorized user sends a non-command message and claude-gemma4 process is detected
- **THEN** router sends the message to the agent pane and returns a short acknowledgment

#### Scenario: Non-command message without agent
- **WHEN** an authorized user sends a non-command message and no claude-gemma4 process is detected
- **THEN** router returns fallback message "agent 未啟用，請使用 /agent start"
