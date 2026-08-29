# stage11-operator-cockpit / todo

## Current Sprint

- [x] 以 `openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis/` formalize #322 已核准的 JOBS 三軸 follow-up，避免再借 `stage11-multi-session-pane-listing-v2` 任務列掛帳
- [x] 保留 `changelog.d/322-cockpit-jobs-three-axis.md`，並補上 `changelog.d/cockpit-jobs-three-axis.md`，讓 #322 handoff 與 canonical delivery preflight 都有對應碎片
- [x] 將 Stage 11 的 JOBS 內容 delta 連回 change spec 與現有 cockpit tests
- [x] 補記 PR #329 已 merged、source issue #322 已 closed 的 closeout bookkeeping，改由 issue #330 專責追蹤 docs-only 收尾

## Blockers

- [x] 程式碼與測試已在 candidate 上落地；本 workstream 此輪只補規格 / 交付關聯，不重做實作
- [ ] merge / issue closure 仍由 Manager 執行後再更新，不在本 todo 先宣告完成
- [x] 本次 closeout 只處理 Stage 11 bookkeeping；原始 implementation 不變，僅補齊 docs-only bookkeeping artifacts（OpenSpec archive metadata / changelog fragment）
- [x] #328 executor/model display 需求仍需獨立 change，未在本 closeout 宣告完成

## Evidence / Links

- [x] 規格變更：`openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis/specs/stage11-operator-cockpit/spec.md`
- [x] 任務追蹤：`openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis/tasks.md`
- [x] 交付碎片：`changelog.d/cockpit-jobs-three-axis.md`
- [x] 既有 #322 碎片：`changelog.d/322-cockpit-jobs-three-axis.md`
- [x] PR #329 已 merged
- [x] issue #322 已 closed
- [x] closeout tracking：`docs/superpowers/workstreams/cockpit-jobs-three-axis-closeout/todo.md`
- [x] OpenSpec tracking：`openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis-closeout/tasks.md`

## Handoff Notes

- [x] `openspec/changes/stage11-multi-session-pane-listing-v2/tasks.md` 已移除 #322 專屬 candidate-only 勾選項，回到 multi-session pane listing 範圍
- [x] Stage 11 operator cockpit 的 closeout 交由 `cockpit-jobs-three-axis-closeout` / #330 收尾
- [ ] 本 repo closeout PR merge 後，GitHub 會依 `Closes #330` 自動關閉 issue #330
- [ ] 若仍需 Cortex remote closure，另由後續 Cortex repo PR 處理，與本 repo 的 #330 issue closure 分開追蹤
- [ ] 若日後要補「實際 executor / model」或更多 JOBS command 契約，請另開新 change
