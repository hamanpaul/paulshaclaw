# stage6-ops-companion-security / plan

- 階段：Stage 6
- 目標：以 `ops-companion` 建立 approval/redaction/audit 安全治理
- 先決依賴：Stage 0 命名 baseline + Stage 1 action path
- 可寫範圍：`paulshaclaw/security/`、`openspec/specs/stage6/`
- 禁止寫入：Stage1 core daemon 核心流程（除 hook）
- 測試 gate：approval flow + redaction fuzz + audit append-only 驗證
