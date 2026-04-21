# stage5-observability-recovery / todo

## Current Sprint

- [x] 補 `docs/ops/recovery.md` 的場景化步驟
- [x] 設定 metrics 預設閾值草案
- [x] 補 raw log 保留與裁切規則

## Blockers

- [x] 已以 Stage1 `/status` 與 Stage2 queue/janitor backlog 作為基線訊號來源

## Evidence / Links

- [x] chaos/restart 測試輸出
- [x] recovery 前後狀態對照（以 chaos matrix + red/green/final logs 表示）

## Handoff Notes

- [x] Stage 6 僅 consume audit 索引，不直接改 Stage 5 指標定義
