# stage7-deploy-three-plane / plan

- 階段：Stage 7
- 目標：落地 core/state/secret 三分部署流程
- 先決依賴：Stage 1 最小可跑版
- 可寫範圍：`paulshaclaw/deploy/`、`paulshaclaw/config/`、`openspec/specs/stage7/`
- 禁止寫入：Stage1~6 執行邏輯（除安裝接點）
- 測試 gate：fresh install/upgrade/uninstall/permission 驗證
