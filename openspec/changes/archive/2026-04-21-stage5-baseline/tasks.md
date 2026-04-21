## 1. OpenSpec change artifacts

- [x] 1.1 完成 `proposal.md`，說明 Stage5 placeholder 補強動機與影響
- [x] 1.2 完成 `design.md`，定義觀測/recovery baseline 設計決策
- [x] 1.3 新增 change delta `specs/stage5/spec.md`

## 2. Stage5 baseline 實作與驗證

- [x] 2.1 建立 `paulshaclaw/observability/` baseline 模組與測試
- [x] 2.2 補齊 `docs/ops/recovery.md` 的 tmux/full restart 操作步驟
- [x] 2.3 產出 Stage5 evidence（red/green/final + chaos matrix）

## 3. Canonical spec 與最終驗證

- [x] 3.1 更新 `openspec/specs/stage5/spec.md` Requirement/Scenario
- [x] 3.2 執行 `python3 -m unittest tests.test_stage5_observability_recovery -v`
- [x] 3.3 執行 `openspec validate stage5-baseline --strict`
