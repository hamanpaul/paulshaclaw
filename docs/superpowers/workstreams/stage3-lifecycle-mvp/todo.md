# stage3-lifecycle-mvp / todo

## Current Sprint

- [x] 開 `openspec` change：`stage3-lifecycle-mvp`
- [x] 實作 schema + `lifecycle.yaml` + static gate script
- [x] 補齊 golden slice 測試資料與 runner 指令

## Blockers

- [x] 已確認 Stage 1 dispatcher 與 Stage 2 memory 的最小介面（`openspec/specs/stage1-core-runtime/spec.md`、`openspec/specs/stage2-memory-governance/spec.md`、`openspec/specs/stage3/spec.md`）

## Evidence / Links

- [x] gate script / schema / template 測試輸出（`evidence/11-schema-template-tests.txt`、`evidence/12-event-replay-tests.txt`）
- [x] golden slice 回歸記錄（`evidence/13-golden-slice-tests.txt`、`evidence/20260421-green-unittest.txt`、`evidence/20260421-final-unittest-discover.txt`）

## Handoff Notes

- [x] 後續 Stage 4 僅 consume phase gate 結果，不反向改 Stage3 schema
