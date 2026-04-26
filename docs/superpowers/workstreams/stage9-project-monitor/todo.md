# stage9-project-monitor / todo

## Current Sprint

- [x] 寫 Phase 1 TDD red 測試（鎖定 config / classifier / parser / `--once` 契約）— 26 tests, all fail with ImportError baseline (`evidence/20260426-red-unittest.txt`)
- [ ] 建立 `paulshaclaw/monitor/` package skeleton 與最小 imports
- [ ] 實作 global config loader（`paulshaclaw.yaml` schema + fallback chain）

## Blockers

- [ ] 確認 paulshaclaw global config 命名（`paulshaclaw.yaml` vs `psc.yaml` vs 其他）— 預設採 `paulshaclaw.yaml`，若操作者偏好 `psc.*` 短寫須在實作前回報
- [ ] 確認 `~/.agents/run/` 目錄是否需在本 stage 建立（目前 §4 layout 未列 `run/`）— 預設由 monitor 在啟動時 `mkdir -p` 並設 0700
- [ ] watchdog 加入 `requirements-stage9.txt`（與 stage11 textual pin 風格一致）

## Evidence / Links

- [x] Phase 1 red unittest log（`evidence/20260426-red-unittest.txt`、`evidence/20260426-red-discover.txt`）
- [ ] Phase 2 green unittest log（`evidence/<date>-green-unittest.txt`）
- [ ] Phase 3 service test log（`evidence/<date>-service-test.txt`）
- [ ] Phase 4 final discover log（`evidence/<date>-final-unittest-discover.txt`）
- [ ] `--once` snapshot 樣本（`evidence/<date>-once-snapshot.json`）
- [ ] subscribe event stream 樣本（`evidence/<date>-subscribe-events.jsonl`）
- [ ] propose 階段 change 包：`openspec/changes/2026-04-26-stage9-project-monitor/`

## Handoff Notes

- [ ] Stage 1 / Stage 3 改用 monitor 為 task source 是後續 change，本 stage 只交付 read API 與 service runtime
- [ ] Stage 11 cockpit 若要加 project-level pane，可消費同一 socket，但屬於後續 follow-up
- [ ] 不擴展 `.paul-project.yml` schema；任何 monitor hint 需求請走另一個 change
- [ ] 違反 single source of truth 原則的提案（例如「monitor 自行記錄專案狀態到 sqlite」）一律拒絕，請改回讀 project artifact
