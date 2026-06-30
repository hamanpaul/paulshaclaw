## Context

完整技術設計見 `docs/superpowers/specs/2026-06-30-120-relay-hook-telegram-wiring-design.md`（v2，已過一輪 codex adversarial review）。本檔摘錄關鍵決策。現況：`psc-relay-hook.sh` 只寫 `PSC_RELAY_TARGET` 檔；codex/copilot 互動回程缺（只有 Claude `bro_in`/`bro_out`）。可複用 `reply_bridge.py`（授權/chunking/binding）與 importer `read_copilot_history` / `read_codex_rollout` / `extract_user_prompts`。

## Goals / Non-Goals

**Goals:**
- manager 自主派工進度（session_start/stop）→ operator Telegram。
- codex/copilot 互動 pane 本輪回覆 → 來源 Telegram user，turn-scoped。
- 複用既有 bridge 與 importer readers，不重造。

**Non-Goals:**
- 去程 `route_to_agent`、Claude `bro_in`/`bro_out`、capture-pane fallback、進度節流。

## Decisions

- **Half 1 gate 於 `PSC_SLICE_ID`**：`psc-relay-hook.sh` 裝在全域 codex/claude config、對所有 session fire；只有 launcher 注入 `PSC_SLICE_ID` 的 manager 派工才推 Telegram，互動 session 天然 no-op（避免灌爆）。收件人不帶 `--source-user-id` → broadcast 到已綁定 operator。
- **Half 2 turn-scoped 自我發現**（取代「session 第一則」）：取本輪 `user_prompts[-1]` 的 `[bro:id]`，無 marker → no-op。因 `route_to_agent` 對每則 routed message 前綴 `[bro:id]`，故 `[-1]` 有 marker ⟺ 本輪由 Telegram 路由。正確處理 first-bro→local、跨輪換 user、first-local→bro。替代方案「綁 session 第一則」會造成跨 user 洩漏 / 漏送（codex review high，已否決）。
- **codex 回覆來源 = Stop event `last_assistant_message`**：`read_codex_rollout` 明示不讀 assistant（`base.py:204-209`），故僅用於取 prompt；copilot 回覆走 `read_copilot_history`（確回 assistant）。
- **讀不到回覆 → skip + log**，不送 `EMPTY_NOTICE`（後者僅保留給「讀得到但空」）。
- **單一 `psc-bro-return.py --platform codex|copilot`**，差異僅 reader + 回覆來源。

## Risks / Trade-offs

- [全域 hook 對所有 session fire，可能誤送] → 兩條皆以 marker（`PSC_SLICE_ID` / `[bro:id]`）gate，互動/本地/headless 各自天然 no-op。
- [codex/copilot transcript 格式各異、tool-turn 可能干擾 `[-1]`] → reader 只回 `role=='user'` 真 prompt；tool-turn 由測試涵蓋；marker 只在真 routed message 出現故不誤判。
- [回程 hook import paulshaclaw.memory] → 沿用 memory hook 的 package-aware venv（與 `codex_session_end.py` 同源），import 可達。
- [進度可能吵] → 先求可見；節流列 follow-up。
