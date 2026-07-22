# Tasks: cockpit-three-layer

## 1. 移除 DETAIL 與 preview 鏈

- [ ] 1.1 `app.py` `compose()` 改三層直排（Header → `#brand-banner` → `#work-list` → `#global-jobs` → Footer），刪 `Horizontal(#main-row)` 與左右 `Vertical`、刪 `#pane-detail` widget
- [ ] 1.2 刪 `_refresh_widgets` 的 detail 渲染段與 `_selected_preview`、建構參數 `preview_loader`、`_loader_accepts_capture_previews`；`_reconcile_state` 收斂為單一 `list-panes` 路徑
- [ ] 1.3 `tmux.py` 刪 `capture_preview` 與 `list_panes` 的 `capture_previews` 分流；`__main__.py` 移除 `preview_loader` 接線
- [ ] 1.4 刪 detail/preview 相關單測；跑既有測試套件確認無回歸

## 2. tcss 三層高度

- [ ] 2.1 `cockpit.tcss`：`#work-list { height: 1fr; min-height: 5; }`、`#global-jobs { height: auto; max-height: 12; overflow-y: auto; }`
- [ ] 2.2 版面測試：三層順序、`#pane-detail` 不存在、80×15 極小終端 WORK ≥5 行（`run_test` 量 region）

## 3. Enter 單一權威與 WorkListView

- [ ] 3.1 新增 `WorkListView(ListView)`：覆寫 `action_select_cursor` 委派 `self.app.action_swap_selected()`；`compose()` 改用之（id 維持 `work-list`）；工作列 ListItem 改附掛 `pane_id`（`WorkItem`）
- [ ] 3.2 移除 `app.on_key` 的 enter 特判（`app.py:582-595`）；app 級 `BINDINGS` enter 保留（footer 顯示＋未 focus 後援）
- [ ] 3.3 Pilot 測試：ListView focused 按 Enter → fake actions 收到恰好一次 swap

## 4. 雙擊偵測

- [ ] 4.1 app 層 `_last_click` 狀態＋可注入 `clock`（預設 `time.monotonic`）；`on_list_view_selected` 實作 0.4s/pane_id 判定
- [ ] 4.2 guards：ownership（`list_view.id` 非 work-list → 不碰狀態；work-list 無 pane_id → 清空）、mismatch（`state.selected_pane` 不符 → 降級首擊）、ACTIVE 列清空、`action_swap_selected` 入口一律先清 `_last_click`、modal 開啟 action 清空
- [ ] 4.3 單測（注入 clock）：命中／逾時／跨列／ACTIVE 清空／三擊新循環／modal 攔截／兩 guard／手勢中斷（C→ACTIVE→C）／範圍鎖定（C→合成非 work-list Selected→C 仍配對）
- [ ] 4.4 Pilot 實鏈測試：`pilot.click` 同列兩次 → fake actions 收到 swap（textual 升版守門）
- [ ] 4.5 唯一 ListView 不變量測試（多檢查點：mount 後、help/manager modal 開啟時與關閉後、refresh tick 後，`query(ListView)` 恰一且 id == work-list）

## 5. restore-before-swap

- [ ] 5.1 app/state 層 `_displacement` 單槽欄位＋activate(C) 演算法（終點 A/B/C/D、liveness 檢查、notify、所有終點接 `_reconcile_state`）；`action_swap_selected` 改走 activate 序列
- [ ] 5.2 fake actions 呼叫序單測：happy path 輪替／被擠者死／現任死／C==displaced 終點 A（恰一次 swap、無 self-swap、記錄 None）／restore 拋錯終點 B（中止、無主 swap、notify、下次 plain swap）／組合分支（C==displaced ∧ restore 拋錯 → 終點 B）／main 拋錯終點 D／連續三 pane 輪替

## 6. JOBS 收合

- [ ] 6.1 `j` binding + toggle 實作：收合 `max_height=3`、title `JOBS ▸ N slices`（N 隨 refresh 刷新）、展開回 auto/max 12、modal 開啟時 inert、in-memory
- [ ] 6.2 測試：toggle 高度斷言（展開 = min(2+rows,12)、收合 ≤3）、收合 title N 刷新、modal 攔截

## 7. 說明與收尾

- [ ] 7.1 footer/help modal 補 `j` 與雙擊說明（`help.py`／BINDINGS descriptions）
- [ ] 7.2 全測試套件通過；本機 tmux 內實跑 cockpit 冒煙（三層版面、雙擊 swap、歸位、`j` 收合）
- [ ] 7.3 同步 `docs/superpowers/specs/2026-07-22-cockpit-three-layer-doubleclick-design.md` 狀態註記（實作完成）
