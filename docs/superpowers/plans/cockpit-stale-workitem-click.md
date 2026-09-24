---
work_item: cockpit-stale-workitem-click
status: accepted
---

# Cockpit WORK 清單 stale click event 防護執行計畫

## Tasks

對應 [hamanpaul/paulshaclaw#375](https://github.com/hamanpaul/paulshaclaw/issues/375)。單一 issue，
非批次工作。accepted 僅表示規格可執行，不表示程式或驗收已完成。詳細根因追蹤與程式碼位置見
`docs/superpowers/specs/cockpit-stale-workitem-click-design.md`。

建議 branch：`feature/375-cockpit-stale-workitem-click`。

- [ ] 在 `paulshaclaw/cockpit/app.py` 的 `WorkListView` 覆寫 `_on_list_item__child_clicked`：
      點擊的 `event.item` 若已不在 `self._nodes`（`NodeList.__contains__`），`event.stop()` 後
      直接 return，不呼叫 `super()`；仍在節點集合內則呼叫 `super()._on_list_item__child_clicked(event)`
      維持原生行為（設定 `index` + 送出 `Selected`）。
- [ ] 新增 regression test：重現「`_refresh_widgets` 的 `clear()` + 重新 `append()` 後，對已移除
      的舊 `WorkItem` 送出子項點擊事件」情境，先在未修復前確認為 RED（拋 `ValueError`），修復後
      GREEN；同時涵蓋「item 仍在節點集合內」的對照案例，確認正常單擊行為不受影響。
- [ ] 驗證既有 WORK 清單相關行為未回歸：單擊高亮、雙擊 swap（`action_swap_selected`）、
      enter 直達 swap（`action_select_cursor`）、pane refresh 觸發的 clear/rebuild 循環。
- [ ] 跑既有 cockpit 測試套件（至少 `tests/test_stage11_operator_cockpit.py` 及涵蓋 WORK 清單
      的相關測試檔）確認全數維持綠燈。
- [ ] 新增 changelog fragment `changelog.d/375-cockpit-stale-workitem-click.md`（type: fix）。
- [ ] PR 內容只涵蓋 `paulshaclaw/cockpit/app.py`、新增測試、changelog fragment；`Closes #375`。

驗收：修復前 regression test 可重現閃退（RED），修復後全數綠燈（GREEN）；既有 cockpit 測試無
回歸；PR 合併後 issue #375 自動關閉。

## Integration gates

本工作為單一 issue（#375）的獨立派工，非批次工作，不涉及其他 work item 的整合。

使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。
只處理本件 issue；所有實作、測試、文件及 changelog 限本件 scope；不修改 Cortex、不升級
Textual、不重寫 `_refresh_widgets` 的整批更新機制（見 spec 的 Boundary）。

採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為
FAIL，接受風險需明文、有界且可追溯。禁止跳 gate 或手改 Cortex registry。部署、發布與本機
skill target 切換由 operator 驗收後執行，不由本 worker 自行進行；不得對外送 Telegram、覆寫
既有 release、變更共享 service/config。PR 可依 Cortex 既有授權 gate 交付；不得僅憑 worker
exit 0 宣告完成。

保留 base/final SHA、RED/GREEN、focused/full tests、review 與 PR 證據。
