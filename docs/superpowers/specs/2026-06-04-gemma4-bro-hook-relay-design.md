# Design: claude-gemma4 bro hook relay

- Date: 2026-06-04
- Status: Approved (brainstorm), pending implementation plan
- Related: PR #54 (skills mirror), #55/#58/#59/#61 (bro tag/trigger evolution), custom-skills #4

## Goal

當 PaulShiaBro daemon 把 Telegram 訊息以 `[bro:<id>] <text>` 路由進 claude-gemma4 的 agent pane 時，讓「該輪的最終回覆」**確定性地**送回該 Telegram 使用者 —— 不靠小模型自己 invoke skill、不在 prompt 裡塞觸發指令。

非 `[bro:...]` 的輸入不做任何中轉。

## Why hooks

Hook 是 Claude Code harness（CLI）層的機制，由 `claude` 程式依 `CLAUDE_CONFIG_DIR/settings.json` 執行，**與模型後端無關**。claude-gemma4 = Claude Code + 換 model backend，因此會執行 `~/.claude-gemma4/settings.json` 的 hooks。Hook 是確定性 shell 指令，不依賴小模型推理，因此遠比「模型自行 invoke skill」可靠；且 `UserPromptSubmit` hook 不輸出內容即可保持 prompt 原樣，零 token 注入。

## Approach (chosen: A — two hooks + per-session statefile)

`UserPromptSubmit` 負責 in、`Stop` 負責 out，透過 per-session statefile 傳遞 source user_id。

替代方案 B（單一 Stop hook 於結束時自 transcript 解析 `[bro:<id>]`）較少元件但需過濾 transcript 中 `tool_result`（同為 user role）的雜訊、且 in 變成隱性判斷；故採 A。

## Components

### 1. `scripts/gemma4-hooks/bro_in.py` — UserPromptSubmit hook
- 讀 stdin JSON：`{ "session_id", "prompt", ... }`。
- `prompt` 開頭符合 `^\s*\[bro:(\d+)\]` → 寫 statefile（見下）`{ "user_id": <int>, "ts": <iso> }`。
- 不符合 → 刪除該 session 的 statefile（清除上一輪殘留，確保非 bro 輪不會誤送）。
- **不輸出任何 stdout**（prompt 原樣、零注入），永遠 `exit 0`。

### 2. `scripts/gemma4-hooks/bro_out.py` — Stop hook
- 讀 stdin JSON：`{ "session_id", "transcript_path", "stop_hook_active", ... }`。
- 若 `stop_hook_active` 為真 → 直接 `exit 0`（防 re-trigger 迴圈）。
- 讀該 session 的 statefile；不存在 → `exit 0`（非 bro 輪，不動作）。
- 存在 → 取 `user_id`；解析 `transcript_path`（jsonl），取**最後一則 `type==assistant` 的純文字內容**（串接其 `content` 中 `type==text` 區塊）。
  - 文字為空 → 用 `（已完成，無文字輸出）`。
- 呼叫 `reply_bridge.py --source-user-id <user_id> --text <text>`。
- 刪除 statefile（消費掉本輪 flag）。
- 永遠 `exit 0`。

### 3. `reply_bridge.py` — 加分段
- `send_reply` 在送出前，若單則 `text` 長度 > Telegram 上限（4096，取保守 4000）→ 依換行盡量切成多段、逐段送出（順序保留）。
- skill 手動使用情境一併受惠。

### 4. daemon `route_to_agent`（`paulshaclaw/core/daemon.py`）
- **移除** `｜用 bro skill 回 --source-user-id <id>` directive，回到精簡：`f"[bro:{user_id}] {text}"`。
- 保留 `[bro:<id>]` tag（hook 的 in 偵測依賴它）。

### 5. bro skill（`custom-skills/bro` + runtime 副本）
- 保留 skill 與 `reply_bridge.py`（供自然語言「用 bro 回覆」情境）。
- **移除 SKILL.md 內「收到 `[bro:<user_id>]` 前綴即自動觸發」那條 When-to-use/description 片段**，避免模型在 hook 之外又 invoke skill 造成**雙重回覆**。

### 6. launcher / 設定
- `config/claude-gemma4-settings.json` 範本加入 `hooks.UserPromptSubmit` 與 `hooks.Stop`，指向 repo 內 hook 腳本絕對路徑。
- `scripts/claude-gemma4` launcher 每次啟動**冪等確保** live `~/.claude-gemma4/settings.json` 含這兩個 hook（比照既有 settings/`.claude.json` 注入方式），達成 repo=runtime、不漂移。

## Data flow

```
Telegram ─▶ daemon.route_to_agent ─ send-keys "[bro:<id>] <text>" ─▶ gemma4 pane
   gemma4 收到 ─▶ [UserPromptSubmit] bro_in 寫 statefile{user_id}
   gemma4 做事（可含多次 tool 呼叫）
   gemma4 該輪結束 ─▶ [Stop] bro_out 讀 statefile + transcript 最後 assistant 文字
                      ─▶ reply_bridge.py --source-user-id <id> ─▶ Telegram
   非 bro prompt ─▶ bro_in 清 statefile ─▶ Stop 找不到 ─▶ 不送
```

## Statefile

- 路徑：`~/.agents/state/bro-hook/<session_id>.json`
- 內容：`{ "user_id": <int>, "ts": "<iso8601>" }`
- 生命週期：`bro_in` 寫入/清除；`bro_out` 讀取後刪除。per-session、單輪消費。
- gemma4 單一 session 一次處理一輪，無併發競態；多 session 以 session_id 區隔。

## Error handling

- 兩個 hook 全程 try/except、**永遠 exit 0** —— hook 失敗不得阻斷 gemma4。
- 錯誤寫入 `~/.agents/log/bro-hook.log`（含 session_id、階段、例外）。
- `reply_bridge.py` 送出失敗（網路/Telegram error）→ 記 log，不重試（避免迴圈/重複）。
- `Stop` 的 `stop_hook_active` 防護避免 hook 連鎖觸發。

## Edge cases

- 反問輪：agent 停下來反問 → `Stop` 照送該問句回 Telegram；使用者的 Telegram 回覆會以新的 `[bro:<id>]` 進來成下一輪。
- 殘留 statefile：每次 `UserPromptSubmit`（非 bro）會清除；`Stop` 用後即刪。
- transcript 無 assistant 文字（只跑工具）→ 送 `（已完成，無文字輸出）`。
- 超長回覆 → `reply_bridge.py` 分段。

## Removed (前面的設計拿掉)

- daemon 每則訊息的 reply directive（#61）。
- skill 內「`[bro:<id>]` 自動觸發」依賴（避免與 hook 雙重回覆）。
- （skill 改名 `bro` 保留，不回退；reply_bridge.py 保留並升級。）

## Testing

- `bro_in`：bro prompt → 寫對的 user_id；非 bro → 清除既有 statefile；壞輸入 → exit 0 不拋。
- `bro_out`：有 statefile → 以 `--dry-run`/mock 驗證 `reply_bridge` 收到正確 `--source-user-id` 與最後 assistant 文字；空文字 → 送提示；無 statefile → 不呼叫；`stop_hook_active` → 不動作。
- `reply_bridge`：>4096 分段段數與順序；≤4096 不變。
- daemon：`route_to_agent` 送出精簡 `[bro:<id>] <text>`（無 directive）。

## Out of scope (YAGNI)

- headless `-p` 中轉（替代架構，本案不採）。
- 跨 session 對話記憶整合、重試佇列、訊息去重持久化（目前單輪消費即足夠）。
