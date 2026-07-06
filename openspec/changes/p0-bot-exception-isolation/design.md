## Context

完整設計：`docs/superpowers/specs/2026-07-06-p0-bot-exception-isolation-design.md`。#196：handler 未知例外殺死 poll loop、無重生、32h 停擺。

## Goals / Non-Goals

**Goals:**
- 單一指令失敗域 = 該指令；listener 永不因 handler 例外退出。
- bot 進程死亡自動重生（backoff）。

**Non-Goals:**
- #195 start.sh SIGKILL 孤兒（另案）。
- per-command timeout budget（後續視需求）。

## Decisions

1. **broad except 放在 dispatch 呼叫點外圈**（非各 handler 內）：一處攔截涵蓋所有現在與未來 handler；既有窄型別 except 留內層語意不變。
2. **錯誤回覆單行、無 traceback/內部路徑**：traceback 進檔案 log；Telegram 只回「指令執行失敗：<例外類別>」——公開通道不洩內部結構。
3. **respawn 放 start.sh**（沿用 dream/cost/manager loop 的 supervisor 慣例）而非 Python 內自我重啟：與既有運維模型一致、失敗域清晰；backoff 5s→30s→120s cap 防 crash-loop 風暴。

## Risks / Trade-offs

- broad except 可能遮住程式性錯誤 → 以 log 完整 traceback + 測試覆蓋補償；不遮 KeyboardInterrupt/SystemExit（顯式放行）。
- respawn 測試需模擬進程退出——用 stub script 方式，避免重演 #195 的 SIGKILL 洩漏情境。
