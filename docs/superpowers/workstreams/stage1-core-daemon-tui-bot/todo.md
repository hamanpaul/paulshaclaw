# stage1-core-daemon-tui-bot / todo

## Current Sprint

- [x] 建立 `core`/`tui`/`bot` 模組邊界清單
- [x] 實作最小啟動流程與設定檔
- [x] 補 stage1 smoke test case 列表

## Blockers

- [x] Stage 0 已提供固定 `opsx:ff` 檢查輸出格式（見 `/.github/prompts/opsx-ff.prompt.md`、`/.claude/commands/opsx/ff.md`）

## Evidence / Links

- [x] stage1 smoke test 執行記錄
- [x] daemon 啟動 log 範例
- [x] `opsx:ff` 固定輸出格式證據（`evidence/20260421-opsx-ff-output-template.md`）

## Handoff Notes

- [x] Stage 3 分支只 consume daemon dispatch，不直接改 Stage1 啟動流程
