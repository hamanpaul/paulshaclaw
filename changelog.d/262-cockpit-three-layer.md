### Changed
- **cockpit 三層直排版面**：移除 DETAIL window 與整條 preview 鏈（`capture-pane` 不再被呼叫，refresh 恆為單次 `list-panes`），版面改上到下三層 banner / WORK / JOBS；WORK `1fr`（min 5 行）、JOBS 隨內容自高（上限 12 行）並支援 `j` 鍵收合（`JOBS ▸ N slices` 一行摘要）。

### Added
- **WORK 滑鼠雙擊 swap**：`WorkListView` 覆寫 `action_select_cursor` 使 `ListView.Selected` 成純滑鼠訊號；app 層 0.4s/pane_id 手動計時偵測雙擊（ownership／mismatch guard、手勢中斷語意），與 Enter 走同一 swap 路徑（單一 action 權威，移除 `on_key` enter 特判）。
- **restore-before-swap 自動歸位**：`_displacement` 單槽記錄，activate 前先把上一個被換走的 pane 歸位（終點 A/B/C/D 全失敗路徑定義），追蹤中錯位任何時刻至多一筆；spec `stage11-operator-cockpit` 同步 3 MODIFIED＋3 ADDED requirements（含 #249「WORK 收斂自身 session」spec 漂移 truth-up）。
