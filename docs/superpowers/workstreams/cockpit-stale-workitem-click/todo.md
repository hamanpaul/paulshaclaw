---
status: proposed
work_item: cockpit-stale-workitem-click
issue: 375
---

# Cockpit WORK 清單 stale click event 防護

對應 [hamanpaul/paulshaclaw#375](https://github.com/hamanpaul/paulshaclaw/issues/375)。

## Problem

WORK `ListView` 在 pane refresh 時會重建列；若舊的 click event 在列移除後才送入 Textual handler，`_nodes.index(event.item)` 會拋出 `ValueError`，造成 Cockpit 閃退。

## Tasks

- [ ] 在 `WorkListView` 的 child-click handler 忽略已不在目前節點集合的 item，且不送出 `Selected`。
- [ ] 新增 stale-item regression test：移除 `row-62` 後送出舊 click event，必須不拋例外。
- [ ] 驗證正常單擊、雙擊切換、pane refresh 與既有 cockpit 測試。
- [ ] 更新 issue #375 的驗證與交付狀態；未完成 commit、PR、merge 或部署前不得宣稱完成。

## Boundary

- 只處理 `paulshaclaw` Cockpit WORK 清單的 stale event 防護與測試。
- 不在本 work item 內升級 Textual、重寫整批清單更新架構或修改 Cortex。
- 原始 production event log 尚未取得，需保留此限制。
