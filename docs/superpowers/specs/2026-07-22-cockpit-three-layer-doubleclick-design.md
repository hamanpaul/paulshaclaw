---
dispatch: hold
slice_id: cockpit-three-layer
plan: null
depends_on: []
---

# Cockpit 三層直排 + 雙擊 swap + 自動歸位 設計

> 日期：2026-07-22 ｜ 狀態：草案（待 codex 對抗審查）｜ 分支：`feature/cockpit-three-layer`
> 範疇：stage11-operator-cockpit spec 修訂。前置脈絡：#248/#249（JOBS 接線、WORK 收斂）、#252（cost footer）皆已 merged。

## 1. 背景與決策脈絡

cockpit 現行版面是左右欄：左 WORK 清單、右 DETAIL（選中 pane 的 metadata + `capture-pane` preview + job 狀態）+ JOBS。本設計評估過兩條演進路線：

- **A 案（否決）**：DETAIL 加 send-keys 輸入列，把 cockpit 變跨 pane 控制台。否決理由：輸入列本質是盲打電傳（無補全、無 TUI 互動、回饋只有 20 行 preview），操作手感不可能贏「swap 過去原生操作」。
- **B 案（採用）**：拿掉 DETAIL，版面改上到下三層（banner / WORK / JOBS），WORK 支援滑鼠雙擊觸發 swap。前提成立：單人 + cortex headless 派工，pane 內無 agent 互動，無他人 client 在看其他 session——「swap 過去看」取代「preview 遠端偷看」沒有副作用。

**swap 可靠性已實測**（tmux 3.4，2026-07-22）：兩個 detached 測試 session（80×24 vs 120×40）跨 session `swap-pane` 600 次，0 失敗、共 1132ms（~1.9ms/次）、pane 數守恆、layout checksum 正常、server 回應正常。原理上 `swap-pane` 是 layout tree 的 O(1) 節點互換，不建立不銷毀狀態，無累積損壞向量。真正的退化是**語意漂移**：奇數次 swap 後 pane 永久留在對方 session（實測確認），故納入 restore-before-swap（§4）把漂移收斂為有界。

## 2. S1 — 版面與移除 DETAIL

- `compose()`（`paulshaclaw/cockpit/app.py:282`）拿掉 `Horizontal(#main-row)` 與左右 `Vertical`，改直排：`Header` → `#brand-banner` → `#work-list` → `#global-jobs` → `Footer`。
- 刪 `#pane-detail` widget 與 `_refresh_widgets` 的 detail 渲染段（`app.py:714-750`）。
- **連根拔 preview 鏈**：`_selected_preview`、建構參數 `preview_loader`、`tmux.py` 的 `capture_preview`、`list_panes` 的 `capture_previews` 分流、`_loader_accepts_capture_previews` 內省 hack 全刪。refresh tick 從此永遠只有一次 `list-panes`（+ 標題缺失 minicom pane 的小 `ps`）。
- 訊息不遺失：degraded 警示 WORK 副標已有（`format_work_pane_subtitle` 的 ⚠）；per-pane job 狀態已在 WORK 列尾綴（`_pane_status`）。DETAIL 底部 `state:` 行與 metadata 行隨 widget 消失，不另遷。
- tcss：`#work-list` 高度 `1fr`；`#global-jobs` `height: auto`、`max-height` ~12 行（含邊框）。

## 3. S2 — 滑鼠雙擊 swap

- **前提已驗證**：tmux `mouse on` 已開；Textual 0.61.1 **無** `Click.chain`（較新版本才有），為此升版風險大於收益 → app 層手動計時偵測。
- 實作：記 `(last_click_monotonic, last_click_index)`（`time.monotonic()`），同一列且間隔 < 0.4s 的第二擊 → 呼叫既有 `action_swap_selected`——與 Enter 走完全同一條路（含 `_background_actions_blocked` 攔截、swap 後 re-scan）。
- 單擊行為不變：`on_list_view_highlighted`（`app.py:412`）既有選取同步。雙擊 ACTIVE 列（首列）與空清單為 no-op。
- 已知小事（不處理）：cockpit pane 未 focus 時首擊被 tmux 拿去 focus pane，第二擊才進 app——正常 tmux 行為。
- spec 修訂：「Enter 是唯一 swap trigger」→「Enter 與 double-click 兩個 trigger，行為等價」。

## 4. S3 — restore-before-swap（自動歸位）

- app/state 層維護**一筆** in-memory 記錄：`(換進 active slot 的 pane_id, 被擠出去的 pane_id)`。
- 換新 pane C 前：
  1. 記錄存在且兩個 pane 都還活著 → 先 `swap 現任 ↔ 被擠者`（現任回家、原住民回 slot），再正常 swap C，更新記錄為 `(C, 原住民)`。
  2. 任一 pane 已消失 → 丟棄記錄、直接 swap（fail-soft，不報錯）。
- 不變量：**任何時刻最多一對 pane 錯位**。pane 以 `%id` 定址（tmux pane id 全生命週期穩定），與位置無關。
- cockpit 重啟記錄歸零，不追殘留漂移。無手動歸位鍵（決策：自動即可）。
- 分層：`actions.py`（`LayoutActionService`）保持純 tmux 指令層不加狀態；歸位排程邏輯放 app/state 層，以 fake actions 驗呼叫序可單測。

## 5. S4 — JOBS 收合

- `j` binding toggle，預設展開。展開 = §2 的 auto 自高；收合 = 只剩 border 標題列（`JOBS ▸ N slices`，slices 數照常隨 refresh 刷新），內容區縮到最小。
- 收合狀態 in-memory，不持久化。modal 開啟時循 `_background_actions_blocked` 攔截。

## 6. 影響面

- **spec delta**（stage11-operator-cockpit）：移除「pane record 須含 preview data」需求；swap trigger 雙軌化；新增三層版面、restore-before-swap、JOBS 收合 requirement。
- **測試**：刪 detail/preview 相關單測；新增（a）雙擊計時——命中、>0.4s 不觸發、跨列不觸發、ACTIVE 列 no-op；（b）歸位——fake actions 驗 swap 呼叫序、pane 消失 fallback；（c）JOBS toggle——展開/收合/副標刷新。
- **不動**：`LayoutActionService` 既有 swap/focus 介面、banner/sysmon/cost 整條（兩段式 tick 節奏照舊）、manager modal、`m`/`t`/`c`/`?`/`q` bindings、`slices_from_status` 與 JOBS 資料來源。

## 7. 開放風險（供對抗審查）

1. 雙擊計時與 Textual 事件模型的互動：0.61 ListView 點擊是否穩定產生可攔截的 click/highlight 事件序（WSL2 + Windows Terminal + tmux 轉發鏈）。
2. restore 的 swap 呼叫序在「被擠者 pane 已死但現任還活著」等半失效狀態下的正確性。
3. `#global-jobs` `height: auto` + `max-height` 在 Textual 0.61 tcss 的實際行為（是否需 `overflow-y: auto`）。
