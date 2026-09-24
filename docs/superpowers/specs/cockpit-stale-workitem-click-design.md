---
work_item: cockpit-stale-workitem-click
status: accepted
---

# Cockpit WORK 清單 stale click event 防護設計

## Decisions

對應 [hamanpaul/paulshaclaw#375](https://github.com/hamanpaul/paulshaclaw/issues/375)。單一 issue，非批次工作。accepted 僅表示規格可執行，不表示程式或驗收已完成。

### 根因鏈（已用程式碼追蹤確認，非臆測）

1. `_refresh_widgets`（`paulshaclaw/cockpit/app.py` 約 L1050）偵測 WORK 清單內容字串
   （`_work_list_items`）與上次快照不同 → `work_list.clear()` 後逐列重新 `append()` 全新
   `WorkItem`。
2. Textual 的滑鼠點擊在內部先產生 `ListItem._ChildClicked` 訊息並排入該 widget 的
   message pump，非同步處理；若 `clear()`／重建剛好插在「使用者點擊」與「訊息被處理」之間，
   訊息裡的 `event.item` 指向的是**已被移除**的舊 `WorkItem` 實例。
3. `ListView._on_list_item__child_clicked`
   （`.venv/lib/python3.12/site-packages/textual/widgets/_list_view.py:299-302`）沒有做存在性
   檢查，直接 `self.index = self._nodes.index(event.item)`；`NodeList.index()`
   （`_node_list.py:74`，繼承 `Sequence` 語意）在找不到元素時拋 `ValueError`，一路往上炸穿
   Textual 的 event loop。
4. `WorkListView`（`app.py` L97）目前只覆寫 `action_select_cursor`（鍵盤 enter 路徑），完全沒碰
   點擊路徑，所以繼承了這個未防護的行為。

### 修復設計

**在 `WorkListView` 覆寫 `_on_list_item__child_clicked`，用 membership check 攔截 stale
item，不動 Textual 本體、不動 `_refresh_widgets` 的 clear/rebuild 機制。**

理由：
- `_refresh_widgets` 的 diff-then-rebuild 是既有、已驗證過的去閃爍機制（見程式內註解），改動它
  風險遠高於在點擊路徑加一個防護判斷；問題根本不在「該不該重建」，而在「重建後舊訊息沒被丟棄」。
- Textual 內建 `ListView` 沒有為子類別開放「點擊時先驗證 item 有效性」的 hook，只能整個覆寫
  `_on_list_item__child_clicked`；`NodeList` 已提供 `__contains__`（`_node_list.py:52`），用
  `event.item in self._nodes` 做顯式判斷比包一層 `try/except ValueError` 更能表達意圖，且不會
  意外吞掉其他非預期的例外。
- 不 monkeypatch site-packages：vendored 補丁會在升級 Textual 時被覆蓋且難以追蹤，本專案其他
  地方也沒有這種先例。

```python
class WorkListView(ListView):
    def action_select_cursor(self) -> None:
        ...  # 既有行為不變

    def _on_list_item__child_clicked(self, event: ListItem._ChildClicked) -> None:
        if event.item not in self._nodes:
            # #375：pane refresh 重建列表期間送達的舊點擊事件；列已被 clear() 移除，
            # 直接呼叫上游 ListView 的邏輯會對 NodeList.index() 拋 ValueError。
            event.stop()
            return
        super()._on_list_item__child_clicked(event)
```

非 stale 的情況完全交給 `super()`，維持與原生 `ListView` 一致的高亮 + `Selected` 行為，
不重新實作 index 賦值與 `post_message` 邏輯（避免兩份邏輯之後跑偏）。

### 測試設計

- Regression test 直接操作 `WorkListView` 實例：mount 若干 `WorkItem`，取其中一個列的
  參照，執行等效於 `_refresh_widgets` 的 `clear()` + 重新 `append()`（新實例，不含剛才那個
  參照），接著建構 `ListItem._ChildClicked(舊 item)` 並呼叫
  `work_list._on_list_item__child_clicked(event)`（或用 Textual Pilot 的訊息注入，視既有
  cockpit 測試慣用手法擇一，維持風格一致）。
- 斷言：不拋例外；`Selected` 未被送出（可用訊息記錄 / mock `post_message` 驗證）；
  `work_list.index` 不等於舊 item 原本的位置。
- 額外跑一個「item 仍在節點集合內」的對照案例，確認正常單擊仍會設定 `index` 並送出
  `Selected`，防止防護判斷把正常路徑也擋掉。
- 全套既有 cockpit 測試（單擊高亮、雙擊 swap、pane refresh、WORK 清單相關案例）需維持綠燈。
