---
dispatch: hold
slice_id: p0-bot-exception-isolation
plan: docs/superpowers/plans/2026-07-06-p0-bot-exception-isolation.md
depends_on: []
---

# P0 — Telegram bot listener 例外隔離 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應 issue：#196
> 規模：S ｜ 獨立於其他 P0/P1 項，可隨時先行

## 1. 背景與問題

`bot/listener.py` 的 command dispatch 只攔窄型別例外；任一 handler 丟未知例外（實例：`/tmate` 逾時 ValueError）會讓 poll loop 整個退出，且無自動重生 → 實際發生 32h 遠端操作面停擺（#196）。這違反 repo 自訂的 fail-close／失敗域分離原則：單一指令的失敗域不應是整個 listener。

## 2. 設計（兩層，皆小）

### 2.1 handler 隔離（主體）
- command dispatch 呼叫點外層加 broad `except Exception`：
  1. 記 log（既有 bot log 通道；含指令名與例外類別、traceback 進檔案 log，不回傳 traceback 給 Telegram）。
  2. 回覆使用者「指令執行失敗：<例外類別>」（單行、不含內部路徑）。
  3. `continue` poll loop——listener 不退出。
- 既有窄型別 except（如 telegram API 重試類）保留在內層，語意不變；broad except 是最外圈保險絲。

### 2.2 殘餘防線：start.sh respawn（bot 限定）
- poll loop 本體（非 handler 區，如網路層意外）退出時，start.sh 對 bot 進程 respawn with backoff（如 5s→30s→120s cap，計數入 log）。
- 沿用 start.sh 既有 supervisor 函式風格（比照 dream/cost/manager loop 的管理慣例）。
- **邊界**：respawn 只管 bot；不動其他 loop、不處理 #195（start.sh 孤兒清理，另案）。

## 3. 測試

- 單元：fake handler 丟 `ValueError` / 任意 `Exception` → listener 續 poll、回覆錯誤訊息、loop 未退出。
- 回歸：既有 telegram listener 測試（含 fail-closed dispatch 守門）零回歸。
- respawn：以 stub script 模擬 bot 進程非零退出 → start.sh 依 backoff 重拉、log 有記錄（測試方式比照既有 start.sh 測試，注意勿引入 #195 的 SIGKILL 洩漏情境）。

## 4. 驗收

- [ ] handler 例外不再殺 listener（單元測試綠）。
- [ ] bot 進程死亡後自動重生（backoff 生效）。
- [ ] #196 關閉。

## 5. 非目標

- #195 start.sh 測試 SIGKILL 孤兒洩漏——另案。
- handler 逾時治理（per-command timeout budget）——如日後 /tmate 類長任務常態化再議。
