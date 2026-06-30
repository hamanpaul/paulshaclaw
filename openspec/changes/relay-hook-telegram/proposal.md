## Why

relay/hook 事件 → Telegram 的轉發端目前完全沒接：manager 自主派工的 `session_start`/`stop` 只寫進 `PSC_RELAY_TARGET` 檔、進不了 Telegram；codex/copilot 互動 pane 的回覆也回不去（只有 Claude 有 `bro_in`/`bro_out`）。#131 已讓 manager 真的自主跑，現在需要把它的進度與 codex/copilot 回覆「看得見」。

## What Changes

- **Half 1 — manager 進度 → Telegram**：`scripts/coordinator/psc-relay-hook.sh` 寫檔後，**gate 於 `PSC_SLICE_ID`**（launcher 注入，互動 session 無此值 → no-op）追加 best-effort `reply_bridge.py --text`（無 `--source-user-id` → broadcast 到已綁定 operator）。
- **Half 2 — codex/copilot 互動回程**：新增 `scripts/gemma4-hooks/psc-bro-return.py`（`--platform codex|copilot`），裝進 codex `Stop` / copilot `agentStop`。**turn-scoped binding**：取本輪 `user_prompts[-1]` 的 `[bro:<id>]` 自我發現 user_id，無 marker → no-op；copilot 回覆走 `read_copilot_history`、codex 回覆走 Stop event payload `last_assistant_message`。讀不到回覆 → log + skip（不送誤導的 `EMPTY_NOTICE`）。
- 安裝接線：codex `Stop` / copilot `agentStop` 以 `managedBy: psc-bro-return` entry nested merge（保留既有 entry）。
- **非目標**：不動去程（`route_to_agent`）；不改 Claude `bro_in`/`bro_out`；capture-pane 末 N 行 fallback 與進度節流為 follow-up。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `coordinator-headless-dispatch`: 「進度 relay 經三家共有 hook」由「寫 relay channel」升級為**實際推送 Telegram**——relay hook 在 `PSC_SLICE_ID` 已設時經 `reply_bridge` broadcast 到 operator；互動 session（無 slice）MUST no-op，不得 spam。
- `agent-conversation-routing`: 「bro 回覆送回 Telegram」由 claude-only 擴及 **codex/copilot 互動 pane**，採 **turn-scoped** 自我發現（本輪 `user_prompts[-1]` 的 `[bro:<id>]`），回程 hook MUST never block agent（exit 0）、讀不到回覆時 MUST skip 而非送 `EMPTY_NOTICE`。

## Impact

- 碼：`scripts/coordinator/psc-relay-hook.sh`、新 `scripts/gemma4-hooks/psc-bro-return.py`、codex/copilot hook 模板與 install 腳本。
- 複用：`custom-skills/bro/scripts/reply_bridge.py`、`paulshaclaw/memory/importer/adapters/base.py`（`read_copilot_history` / `read_codex_rollout` / `extract_user_prompts`）。
- 測試：`tests/test_coordinator_relay_hook.py` 擴充、新 `tests/test_psc_bro_return.py`。
- 設計：`docs/superpowers/specs/2026-06-30-120-relay-hook-telegram-wiring-design.md`。
- issue：Closes #120（併 #89）；umbrella #14。
