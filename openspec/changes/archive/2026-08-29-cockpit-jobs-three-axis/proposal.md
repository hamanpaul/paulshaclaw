## Why

#322 的 JOBS 三軸實作、回歸測試與 `changelog.d/322-cockpit-jobs-three-axis.md` 已在
candidate 上落地，但 canonical delivery preflight 仍缺少與 change slug 同名的
`changelog.d/cockpit-jobs-three-axis.md`，而上一輪交付又把其餘 bookkeeping 暫掛進
`openspec/changes/stage11-multi-session-pane-listing-v2/tasks.md`。那個 Stage 11 change
仍在處理 multi-session pane listing，本身不是 #322 的真相源；繼續把 #322 勾選項塞在
裡面，會讓 active tasks 混入無關範圍，也讓 `stage11-operator-cockpit` 缺少專屬的
JOBS 三軸 spec delta 與 workstream todo 關聯。

這個 change 的目的，是把已核准的 #322 follow-up 獨立成專用 OpenSpec 變更，僅 formalize
pre-archive 交付；不在這裡提前宣告 archive、merge、issue closure 或「Manager 已完成」。

## What Changes

- 新增專用 OpenSpec change `cockpit-jobs-three-axis`，記錄 #322 已落地的
  JOBS workflow-run ingest、project/stage/agent 三軸、排序/計數與 safe detail 行契約。
- 新增 `docs/superpowers/workstreams/stage11-operator-cockpit/todo.md`，把 Stage 11
  JOBS follow-up 的 spec、tasks、`changelog.d/cockpit-jobs-three-axis.md`，以及既有
  `changelog.d/322-cockpit-jobs-three-axis.md` 串在同一個 workstream。
- 從 `stage11-multi-session-pane-listing-v2` 移除 #322 專屬交付任務，讓該 change 回到
  原本的 multi-session pane listing 範圍。

## Capabilities

### Modified Capabilities

- `stage11-operator-cockpit`: 補上 JOBS 三軸內容、workflow-run / `not_claimable`
  ingest、排序與 detail 行的需求描述。

## Impact

- 只改 OpenSpec、workstream 與 canonical changelog bookkeeping；不改既有 cockpit 程式碼，
  並保留已核准的 #322 changelog 內容。
- Manager 仍保留 archive / merge / issue closure 的唯一權威；本 change 只描述
  pre-archive 狀態。
