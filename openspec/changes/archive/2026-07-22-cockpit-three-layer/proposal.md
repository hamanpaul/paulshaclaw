# Proposal: cockpit-three-layer

## Why

cockpit 現行左右欄版面中，右欄 DETAIL 的遠端 preview 價值已因使用情境改變而消失（單人 + cortex headless 派工，pane 內無 agent 互動；swap 過去原生操作勝過盲看 20 行 preview），且雙欄擠壓 WORK 清單寬度。同時 swap 缺滑鼠捷徑、且跨 session swap 會累積 pane 歸屬漂移。設計已於 `docs/superpowers/specs/2026-07-22-cockpit-three-layer-doubleclick-design.md` 定稿（codex 對抗審查 8 輪 PASS），本 change 據以落地。

## What Changes

- **移除 DETAIL window**：刪 `#pane-detail` widget 與整條 preview 鏈（`capture_preview`、`preview_loader`、`capture_previews` 分流、`_loader_accepts_capture_previews`），refresh tick 永遠只剩一次 `list-panes`。
- **版面改三層直排**：banner → WORK（`1fr`、`min-height: 5`）→ JOBS（`height: auto`、`max-height: 12`）。
- **WORK 滑鼠雙擊 swap**：`WorkListView(ListView)` 覆寫 `action_select_cursor` 使 `Selected` 成純滑鼠訊號；app 層手動計時（0.4s、pane_id key、可注入 clock）偵測雙擊，觸發既有 `action_swap_selected`；含 ownership／mismatch guard 與手勢中斷語意。移除 `app.on_key` 的 enter 特判（單一 action 權威）。
- **restore-before-swap 自動歸位**：`_displacement` 單槽 in-memory 記錄，activate(C) 演算法（終點 A/B/C/D）保證追蹤中錯位任何時刻至多一筆；重啟歸零。
- **JOBS 收合**：`j` binding toggle，預設展開，收合高度 ≤3。
- **BREAKING（TUI 行為）**：DETAIL 面板與其 preview 顯示消失；Enter 行為不變。

## Capabilities

### New Capabilities

（無——全部屬既有 stage11 operator cockpit capability 的需求修訂）

### Modified Capabilities

- `stage11-operator-cockpit`：(1) pane 枚舉需求刪去 preview data 欄位；(2)「Enter 為唯一 swap trigger」改為 Enter 與 double-click 雙 trigger、行為等價，並前置 restore-before-swap 序列；(3) 新增三層直排版面（移除 DETAIL）requirement；(4) 新增 restore-before-swap requirement；(5) 新增 JOBS 收合 requirement；(6) footer/modal 說明納入 `j` 與雙擊。

## Impact

- **程式碼**：`paulshaclaw/cockpit/app.py`（compose、widgets、bindings、雙擊偵測、activate 演算法）、`paulshaclaw/cockpit/tmux.py`（刪 `capture_preview` 與分流）、`paulshaclaw/cockpit/cockpit.tcss`（三層高度規則）、`paulshaclaw/cockpit/__main__.py`（`preview_loader` 接線移除）。
- **測試**：刪 detail/preview 單測；新增雙擊計時、guard、手勢中斷、restore 呼叫序（含終點 A/B 與組合分支）、JOBS toggle 高度、唯一 ListView 不變量（多檢查點）、Enter 單一權威 Pilot 測試。
- **不動**：`LayoutActionService` 介面、banner/sysmon/cost 鏈、manager modal 與 control client、`m`/`t`/`c`/`?`/`q` bindings。
- **依賴**：無新增（textual 維持 0.61.1，不升版）。
