## 1. OpenSpec change artifacts

- [x] 1.1 完成 `proposal.md`，說明 Stage7 baseline 範圍與影響
- [x] 1.2 完成 `design.md`，定義三分部署與權限檢查決策
- [x] 1.3 新增 change delta `specs/stage7/spec.md`

## 2. Stage7 baseline 實作與驗證

- [x] 2.1 建立 `paulshaclaw/deploy/` 與 CLI 命令骨架
- [x] 2.2 新增 template catalog 與 rename 規則
- [x] 2.3 新增 state/secret 權限檢查與 secret install flow
- [x] 2.4 新增 rollback checkpoints/actions baseline 與測試

## 3. Canonical spec 與最終驗證

- [x] 3.1 更新 `openspec/specs/stage7/spec.md` Requirement/Scenario
- [x] 3.2 執行 `python3 -m unittest tests.test_stage7_deploy_three_plane -v`
- [x] 3.3 執行 `openspec validate stage7-baseline --strict`
