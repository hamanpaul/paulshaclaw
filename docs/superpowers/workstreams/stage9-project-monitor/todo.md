# stage9-project-monitor / todo

## Current Sprint

- [x] 寫 Phase 1 TDD red 測試（鎖定 config / classifier / parser / `--once` 契約）— 26 tests, all fail with ImportError baseline (`evidence/20260426-red-unittest.txt`)
- [x] 建立 `paulshaclaw/monitor/` package skeleton 與最小 imports — models/config/scanner/parser/__main__ 全部就位
- [x] 實作 global config loader（`paulshaclaw.yaml` schema + fallback chain）— `--config` flag → `PAULSHACLAW_CONFIG` env → `~/.config/paulshaclaw/paulshaclaw.yaml` → bundled sample
- [x] Phase 2 Green 完成：26/26 stage9 tests pass、90/90 discover OK（2 skip 為 stage11 預期）
- [x] Phase 3：service runtime（filesystem watcher + Unix socket server + subscribe stream）— `service.py` + `server.py` + `watcher.py` + `snapshot.py` 上線，service tests 綠燈（`evidence/20260426-phase3-service-test.txt`）
- [x] Phase 4：Cortex extraction 後改採歷史封存；不把已遷出的 capability 落到本 repo canonical specs

## Blockers

- [x] paulshaclaw global config 命名 → 採 `paulshaclaw.yaml`（操作者 2026-04-26 確認用預設）
- [x] `~/.agents/run/` 目錄處理 → monitor 啟動時 `mkdir -p` + `chmod 0700`（操作者 2026-04-26 確認用預設）
- [x] `requirements-stage9.txt` 加入 `watchdog>=3.0.0` 與 `PyYAML>=6.0`

## Evidence / Links

- [x] Phase 1 red unittest log（`evidence/20260426-red-unittest.txt`、`evidence/20260426-red-discover.txt`）
- [x] Phase 2 green unittest log（`evidence/20260426-green-unittest.txt`、`evidence/20260426-green-discover.txt`）
- [x] Phase 2 `--once` snapshot 樣本（`evidence/20260426-once-snapshot.json` — monitor 對自身 worktree 的 90+ 行 JSON snapshot）
- [x] Phase 3 service test log（`evidence/20260426-phase3-service-test.txt`）
- [x] 全量 discover log（`evidence/20260426-phase3-final-discover.txt`）
- [ ] `--once` snapshot 樣本（`evidence/<date>-once-snapshot.json`）
- [x] subscribe event stream 樣本（`evidence/20260426-phase3-subscribe-events.jsonl`）
- [x] change 包已封存：`openspec/changes/archive/2026-07-25-2026-04-26-stage9-project-monitor/`

## Handoff Notes

- [x] monitor runtime / config / read API 已遷至 `paulsha-cortex`；本 repo 僅保留 shim、依賴 pin 與部署整合
- [x] Stage 1 / Stage 3 / cockpit 的後續 monitor 整合改由 Cortex ownership 與本 repo integration boundary 管理
- [ ] 不擴展 `.paul-project.yml` schema；任何 monitor hint 需求請走另一個 change
- [ ] 違反 single source of truth 原則的提案（例如「monitor 自行記錄專案狀態到 sqlite」）一律拒絕，請改回讀 project artifact
