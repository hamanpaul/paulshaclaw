# stage11-operator-cockpit / todo

## Current Sprint

- [x] JOBS 三軸重設計已由 PR #329 合併，對應 source issue #322 已關閉
- [x] Stage 11 closeout bookkeeping 改由 issue #330 專責追蹤，不回頭改動既有 implementation

## Blockers

- [x] 本次 closeout 只處理 Stage 11 bookkeeping；原始實作不變，僅補齊 docs-only bookkeeping artifacts（OpenSpec archive metadata / changelog fragment）
- [x] #328 executor/model display 需求仍需獨立 change，未在本 closeout 宣告完成

## Evidence / Links

- [x] PR #329 已 merged
- [x] issue #322 已 closed
- [x] closeout tracking：`docs/superpowers/workstreams/cockpit-jobs-three-axis-closeout/todo.md`
- [x] OpenSpec tracking：`openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis-closeout/tasks.md`

## Handoff Notes

- [x] Stage 11 operator cockpit 的 closeout 交由 `cockpit-jobs-three-axis-closeout` / #330 收尾
- [ ] 本 repo closeout PR merge 後，GitHub 會依 `Closes #330` 自動關閉 issue #330
- [ ] 若仍需 Cortex remote closure，另由後續 Cortex repo PR 處理，與本 repo 的 #330 issue closure 分開追蹤
