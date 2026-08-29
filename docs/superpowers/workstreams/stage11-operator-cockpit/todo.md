# stage11-operator-cockpit / todo

## Current Sprint

- [x] 以 `openspec/changes/cockpit-jobs-three-axis/` formalize #322 已核准的 JOBS 三軸 follow-up，避免再借 `stage11-multi-session-pane-listing-v2` 任務列掛帳
- [x] 保留 `changelog.d/322-cockpit-jobs-three-axis.md`，並補上 `changelog.d/cockpit-jobs-three-axis.md`，讓 #322 handoff 與 canonical delivery preflight 都有對應碎片
- [x] 將 Stage 11 的 JOBS 內容 delta 連回 change spec 與現有 cockpit tests

## Blockers

- [x] 程式碼與測試已在 candidate 上落地；本 workstream 此輪只補規格 / 交付關聯，不重做實作
- [ ] archive / merge / issue closure 仍由 Manager 執行後再更新，不在本 todo 先宣告完成

## Evidence / Links

- [x] 規格變更：`openspec/changes/cockpit-jobs-three-axis/specs/stage11-operator-cockpit/spec.md`
- [x] 任務追蹤：`openspec/changes/cockpit-jobs-three-axis/tasks.md`
- [x] 交付碎片：`changelog.d/cockpit-jobs-three-axis.md`
- [x] 既有 #322 碎片：`changelog.d/322-cockpit-jobs-three-axis.md`

## Handoff Notes

- [x] `openspec/changes/stage11-multi-session-pane-listing-v2/tasks.md` 已移除 #322 專屬 candidate-only 勾選項，回到 multi-session pane listing 範圍
- [ ] 若日後要補「實際 executor / model」或更多 JOBS command 契約，請另開新 change
