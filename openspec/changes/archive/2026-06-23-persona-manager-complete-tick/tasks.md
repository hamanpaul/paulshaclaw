# Tasks

> 詳細逐步 TDD（含完整程式碼）見 `docs/superpowers/plans/2026-06-23-persona-manager-complete-tick.md`。本檔為 apply 追蹤用的高階 checklist。

## 1. 分支與骨架

- [x] 1.1 分支 `feature/121-manager-complete-tick`（已開）
- [x] 1.2 建 `tests/test_coordinator_manager.py` + `FakeDispatcher`，寫 done→passed manifest failing test（RED）
- [x] 1.3 建 `paulshaclaw/coordinator/manager.py`：`complete_tick` + `GateRunner` + `_default_gate_runner` + `_utcnow`，使測試 GREEN
- [x] 1.4 commit

## 2. 完成分類與 in-flight

- [x] 2.1 加 failed→failed manifest 測試
- [x] 2.2 加 in-flight（仍 dispatched）不終結、不寫檔測試
- [x] 2.3 跑測試確認 GREEN（Task 1 實作已涵蓋），commit

## 3. reconciliation 與冪等

- [x] 3.1 加「終態但缺 manifest 補寫」測試
- [x] 3.2 加 tick 重跑冪等（不覆寫 `completed_at`、不重複 poll）測試
- [x] 3.3 跑測試確認 GREEN，commit

## 4. shadow gate 觀測

- [x] 4.1 加「gate 判 ok=False 仍 passed、`gate_verdict` 如實記錄」測試
- [x] 4.2 加「gate_runner 例外吞掉、`gate_verdict=null`、`gate_status` 不變」測試
- [x] 4.3 跑測試確認 GREEN，commit

## 5. 例外隔離與下游釋放

- [x] 5.1 加 per-job poll 例外隔離測試（一個爆、另一個仍完成、爆的進 `errors`）
- [x] 5.2 加「寫出 passed manifest 後注入 metas → summary `released` 含下游、`default_is_satisfied` 回 True」測試
- [x] 5.3 跑測試確認 GREEN，commit

## 6. CLI complete 子命令

- [x] 6.1 建 `tests/test_coordinator_cli_complete.py`：`complete` 子命令 smoke failing test（RED）
- [x] 6.2 改 `paulshaclaw/coordinator/cli.py`：import `manager`、加 `complete` parser（`--handoff-dir`/`--specs-dir`）與 handler，使測試 GREEN
- [x] 6.3 commit

## 7. 全套件驗證

- [x] 7.1 跑 coordinator + persona 相關套件，確認未回歸派工側/autonomy
- [x] 7.2 跑完整 `tests/` + `paulshaclaw/memory/tests/`，確認基線不減
- [x] 7.3 進 code review gate（`/codex:adversarial-review`）
