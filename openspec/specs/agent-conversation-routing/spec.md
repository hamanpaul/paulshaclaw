# agent-conversation-routing Specification

## Purpose
Route Telegram non-command messages to the running claude-gemma4 agent pane, and relay the agent's reply back to the source Telegram user.
## Requirements
### Requirement: Non-command messages routed to agent pane when running
The system SHALL route Telegram non-command messages to the claude-gemma4 agent pane via `tmux send-keys` when an agent process is detected in the process tree.

#### Scenario: Message forwarded to running agent
- **WHEN** operator sends a non-command message and claude-gemma4 process is detected
- **THEN** system sends `[bro:<user_id>] <text>` to the agent pane via tmux send-keys and replies to Telegram with `"…"`

#### Scenario: Message format includes source user ID
- **WHEN** operator sends a non-command message to a running agent
- **THEN** the text sent to the agent pane MUST be the lean form `[bro:<user_id>] <text>` (no in-prompt reply directive)
- **AND** the `[bro:<user_id>]` tag MUST carry the Telegram user ID so the claude-gemma4 hooks can relay the reply with `--source-user-id`

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

### Requirement: codex/copilot 互動 pane 的 bro 回覆以 turn-scoped 自我發現送回 Telegram

系統 SHALL 為 codex 與 copilot 互動 pane 提供回程：經 codex `Stop` / copilot `agentStop` hook（單一 `psc-bro-return.py`，以 `--platform codex|copilot` 參數化），以**本輪** `user_prompts[-1]` 的 `[bro:<user_id>]` marker 自我發現收件 user，並將本輪最終 assistant 回覆經 `reply_bridge.py --source-user-id <user_id>` 送回該 Telegram chat。回程 hook MUST never block agent（always exit 0）、MUST log failures rather than raise。本輪回覆讀不到時 MUST skip 而非送 `（已完成，無文字輸出）`。本需求 MUST NOT 改變 Claude 既有 `bro_in`/`bro_out` 行為。

#### Scenario: 本輪由 Telegram 路由 → 送回該 user
- **WHEN** codex/copilot 互動 pane 本輪 `user_prompts[-1]` 以 `[bro:<user_id>]` 開頭且該輪完成
- **THEN** 本輪最終 assistant 回覆經 `reply_bridge.py --source-user-id <user_id>` 送回該 user 的 Telegram chat（copilot 回覆取自 `read_copilot_history`、codex 回覆取自 Stop event payload `last_assistant_message`）

#### Scenario: 本輪為本地輸入 → 不送（turn-scoped）
- **WHEN** 本輪 `user_prompts[-1]` 不以 `[bro:<user_id>]` 開頭（本地輸入，或無 marker 的 manager headless job）
- **THEN** 不發生 Telegram 回程

#### Scenario: 同 session 跨輪換 user → 送給本輪 user
- **WHEN** 前一輪 prompt 為 `[bro:111]`、本輪 `user_prompts[-1]` 為 `[bro:222]`
- **THEN** 回覆送給 `222`，不被前一輪的 `111` 綁定

#### Scenario: 本輪回覆讀不到 → skip 不誤送
- **WHEN** codex Stop event 缺 `last_assistant_message`（或 copilot history 缺檔／壞檔）導致本輪回覆讀不到
- **THEN** hook 記 log 並 skip，MUST NOT 送 `（已完成，無文字輸出）`

#### Scenario: 回覆讀得到但為空 → 送 EMPTY_NOTICE
- **WHEN** 本輪回覆讀得到但為空字串（純 tool 輸出）
- **THEN** 送 `（已完成，無文字輸出）` 給本輪 user

