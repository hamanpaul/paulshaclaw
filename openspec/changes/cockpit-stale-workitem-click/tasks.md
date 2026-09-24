## 1. cockpit-stale-workitem-click

- [x] T1 (RED): 在 `tests/test_stage11_operator_cockpit.py` 新增 stale `WorkItem` child-click 回歸測試，重現 `_refresh_widgets()` clear/append 重建後舊列晚到事件曾觸發的 `ValueError`。
- [x] T2: 在 `paulshaclaw/cockpit/app.py` 讓 `WorkListView._on_list_item__child_clicked` 對已不在 `self._nodes` 的 stale 列先 `event.stop()` 並直接返回，現役列則維持 Textual 原生處理。
- [x] T3: 新增 non-stale control case，確認單擊仍會更新 highlight / selection 並保留 `Selected` 事件流。
- [x] T4: 執行 WORK list 聚焦驗證，涵蓋 `tests/test_stage11_operator_cockpit.py` 與既有雙擊/enter/refresh 相關測試。
- [x] T5: 完成交付附帶項目：
  - [x] 新增 changelog fragment `changelog.d/375-cockpit-stale-workitem-click.md`。
  - [ ] 在 PR metadata 加上 `Closes #375`。
