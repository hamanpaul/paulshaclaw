# Design: cockpit-three-layer

> 權威設計文件：`docs/superpowers/specs/2026-07-22-cockpit-three-layer-doubleclick-design.md`（v8 定稿，codex 對抗審查 8 輪 PASS）。本檔為 openspec 摘要投影；細節、原始碼佐證行號與逐輪審查裁決以該文件為準。

## Context

cockpit（`paulshaclaw/cockpit/`，textual 0.61.1 TUI）現為左右欄：左 WORK 清單、右 DETAIL（metadata + `capture-pane` preview + job 狀態）+ JOBS。使用情境已變：單人 + cortex headless 派工，pane 內無 agent 互動——preview 遠端偷看的價值消失，「swap 過去原生操作」是更好的 peek 手段。tmux `swap-pane` 可靠性已實測（3.4，跨 session 600 次 0 失敗），真正的退化是語意漂移（奇數次 swap 後 pane 留在對方 session）。

## Goals / Non-Goals

**Goals:**
- 版面三層直排（banner / WORK / JOBS），移除 DETAIL 與整條 preview 鏈
- WORK 滑鼠雙擊觸發 swap（與 Enter 等價）
- restore-before-swap：追蹤中錯位任何時刻至多一筆
- JOBS `j` 收合

**Non-Goals:**
- 不升版 textual（維持 0.61.1）
- 不做 send-keys 跨 pane 輸入（A 案已否決）
- 不持久化 displacement／收合狀態；不做啟動時漂移修復；不設手動歸位鍵
- 不動 `LayoutActionService` 介面、banner/sysmon/cost 鏈、manager modal

## Decisions

1. **`Selected` 成純滑鼠訊號**：`WorkListView(ListView)` 覆寫公開 action `action_select_cursor` 直接委派 `app.action_swap_selected()`（不 post `Selected`）。棄 namespace 重綁方案——覆寫公開 method 不碰私有 API、不依賴 binding 字串解析。binding 優先序有 `screen.py:298-341` 佐證（focused-first、同鍵先入者勝）；`_list_view.py` 僅 `:273`/`:303` 兩處 post `Selected`，repo 零程式化呼叫點。
2. **雙擊偵測在 app 層 `on_list_view_selected`**：0.61 無 `Click.chain` → 手動計時（0.4s、`pane_id` key、可注入 clock）。ownership guard（`list_view.id`＋`pane_id` getattr）、mismatch guard（`state.selected_pane` 不符降級首擊）、手勢中斷語意（ACTIVE 列／無 pane_id 點擊清空 `_last_click`；非 work-list 事件不碰狀態——現 UI 唯一 ListView 即 work-list，等價性以多檢查點 `query(ListView)` 不變量測試守護）。`_last_click` 清理點單一化：任何來源觸發 `action_swap_selected` 一律先清。移除 `app.on_key` enter 特判。
3. **activate(C) 演算法（終點 A/B/C/D）**：`_displacement` 單槽；restore 成功且 `C == displaced` → 終點 A（免主 swap）；restore 失敗 → 終點 B（中止、不做主 swap、重試即 plain swap）；liveness 缺 → 丟棄記錄直接主 swap；所有終點接全量 re-scan。序列化依據＝Textual 單執行緒事件迴圈＋同步 subprocess。分層：actions.py 維持無狀態，演算法在 app/state 層。
4. **tcss 數字釘死**：`#work-list { height: 1fr; min-height: 5; }`；`#global-jobs { height: auto; max-height: 12; overflow-y: auto; }`（內容已有 `rows[:10]` 上限）；收合 `max_height = 3`。

## Risks / Trade-offs

- [排隊壓縮：慢擊被壓成雙擊] → 無硬上限、無兜底；影響分析（一次可逆 swap、追蹤有效時下次 activate 歸位）後明文接受列管。
- [`Selected×2 → swap` 因果邊：意外訊息重複被升級為 layout 變動] → 雙擊功能定義本身；影響有界（單次可逆 candidate swap）、現系統無非滑鼠 producer，接受列管。
- [脫離追蹤殘留（restore 失敗／liveness 丟棄／process 結束）] → 累積上限＝三者次數和；單人環境手動收拾，接受。
- [未來新增第二個 ListView 破壞手勢範圍等價性] → 多檢查點不變量測試紅燈＋設計註記強制重裁決。
- [textual 升版改變 `Selected`-on-click 語意] → Pilot 實鏈測試充當升版守門。

## Migration Plan

單 PR 落地（TUI 行為變更、無資料遷移）。回滾＝revert PR。部署沿既有 cockpit 重啟程序（tmux pane 內重啟 `python -m paulshaclaw.cockpit`）。

## Open Questions

（無——8 輪對抗審查後全數關閉或明文接受）
