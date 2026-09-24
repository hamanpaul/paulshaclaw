---
work_item: cockpit-stale-workitem-click
status: accepted
---

# Cockpit WORK 清單 stale click event 防護規格

## Requirements

對應 [hamanpaul/paulshaclaw#375](https://github.com/hamanpaul/paulshaclaw/issues/375)。單一 issue，非批次工作。accepted 僅表示規格可執行，不表示程式或驗收已完成。

### Problem（已循程式碼追蹤確認）

`paulshaclaw/cockpit/app.py` 的 `WorkListView`（約 L97）繼承 Textual `ListView`，只覆寫
`action_select_cursor`，未覆寫點擊路徑。`_refresh_widgets`（約 L1050-L1075）在 WORK 清單內容
變動時執行 `work_list.clear()` 再重新 `append()` 全新 `WorkItem` 實例。

Textual 內建 `ListView._on_list_item__child_clicked`
（`.venv/lib/python3.12/site-packages/textual/widgets/_list_view.py:299-302`）在收到子項點擊
訊息時執行 `self.index = self._nodes.index(event.item)`。若使用者點擊發生在 `clear()` 與訊息
處理之間（訊息已入 Textual message pump，但列已被移除重建），`event.item` 已不在
`self._nodes`（`NodeList`，見 `_node_list.py:20`），`NodeList.index()` 會拋 `ValueError`，
未被任何地方攔截，導致 Cockpit 閃退。

### 修復需求

1. 在 `WorkListView` 覆寫子項點擊 handler（`_on_list_item__child_clicked` 或等效攔截點），
   於呼叫 `self._nodes.index(event.item)` 前先確認 `event.item` 仍在 `self._nodes` 內
   （`NodeList` 已提供 `__contains__`，見 `_node_list.py:52`）。
2. 若判定為 stale（item 已不在目前節點集合）：`event.stop()`、不改動 `self.index`、不
   `post_message(Selected(...))`、不拋例外。
3. 若 item 仍在節點集合內，行為必須與 Textual 原生 `ListView` 完全一致（正常單擊高亮 +
   送出 `Selected`），不得改變既有雙擊 swap（`action_swap_selected`）與 `action_select_cursor`
   （enter 直達 swap）行為。
4. 新增 regression test：模擬 `_refresh_widgets` 的 `clear()` + 重新 `append()` 流程，取得
   一個已被移除的舊 `WorkItem` 實例，直接對 `WorkListView` 送出對應的子項點擊訊息（或直接呼叫
   handler），斷言：不拋例外、`Selected` 訊息未被送出、`index` 未被改動成該項目位置。
5. 既有 cockpit 測試（含 WORK 清單單擊、雙擊切換、pane refresh 相關案例）需全數維持綠燈。

### Boundary

- 只處理 `paulshaclaw` Cockpit WORK 清單（`WorkListView`）的 stale click event 防護與其
  regression test。
- 不升級 Textual 版本、不修改或 monkeypatch site-packages 內的 Textual 原始碼、不重寫整批
  WORK 清單更新架構（`_refresh_widgets` 的 diff-then-rebuild 機制維持原樣）。
- 不修改 Cortex、不修改 JOBS 面板（`JobsPanel`/`jobs_panel.py`）等其他面板的點擊路徑，除非
  它們共用同一段會拋例外的程式碼（目前追蹤結果顯示 JOBS 走 `Tree`，非 `ListView`，不在範圍內）。
- 原始 production event log（issue 描述的實際閃退現場）尚未取得，修復與測試以程式碼追蹤出的
  根因（Textual `ListView._on_list_item__child_clicked` 對已移除節點呼叫 `.index()`）為準。

### 驗收

- 新增 regression test 在修復前重現 `ValueError`（RED），修復後綠燈（GREEN）。
- 全套既有 cockpit 相關測試（`tests/test_stage11_operator_cockpit.py` 等）持續通過。
- PR 完成後 `Closes #375`。
