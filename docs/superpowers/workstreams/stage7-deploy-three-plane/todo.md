# stage7-deploy-three-plane / todo

## Current Sprint

- [x] 補齊 template 檔清單與 rename 規則
- [x] 定義 secret install 互動步驟
- [x] 定義 rollback 還原策略與檢查點

## Blockers

- [x] Stage 1 最小可跑版產物定義已足夠作為 Stage 7 consume 邊界

## Evidence / Links

- [x] install/upgrade/uninstall 測試記錄（`evidence/20260421-red-unittest.txt`、`evidence/20260421-green-unittest.txt`、`evidence/20260421-final-unittest-discover.txt`）
- [x] 權限檢查與 secret install 輸出記錄（同 `evidence/20260421-green-unittest.txt`）
- [x] TDD 摘要（`evidence/03-tdd-summary.md`）

## Handoff Notes

- [x] Stage 8/10 延後，不在 Stage 7 內引入成本治理或 protocol 演進
- [x] 本階段只交付可驗證 baseline；若要接真實 installer，需補檔案 owner/group 與實體 rollback artifact 管理
