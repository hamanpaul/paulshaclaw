## ADDED Requirements

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
