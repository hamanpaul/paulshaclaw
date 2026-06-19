## Context

Stage5 工作流需要把 Stage1/Stage2 的健康訊號轉成可驗證觀測基線，同時提供 recovery 可操作手冊。既有 `docs/superpowers/workstreams/stage5-observability-recovery/` 已定義任務，但 OpenSpec 尚未具體化 Requirement/Scenario。

## Goals / Non-Goals

**Goals:**
- 讓 Stage5 具備可驗收 spec 條款與測試對應。
- 固定 health report / error record / raw log policy 最小格式。
- 定義 tmux crash 與 full runtime restart 的文件化復原流程。
- 提供 chaos matrix 最小驗證矩陣與 evidence 歸檔規則。

**Non-Goals:**
- 不在 Stage5 導入新 UI dashboard。
- 不實作完整 secrets redaction 引擎（先提供 raw log 裁切基線）。
- 不修改 Stage1 啟動流程或 Stage2 治理路徑。

## Decisions

### Decision 1：以 baseline API + 文件雙軌交付

- **選擇**：在 `paulshaclaw/observability/baseline.py` 提供可測 API，並在 `docs/ops/recovery.md` 提供操作手冊。
- **理由**：可同時滿足程式可驗證與人工作業可執行。

### Decision 2：錯誤記錄先固定 schema 版本

- **選擇**：`schema_version` 固定 `stage5.error.v1`。
- **理由**：避免 Stage6 稽核索引階段發生欄位漂移。

### Decision 3：raw log 採 head/tail 裁切

- **選擇**：payload 超限時保留 head/tail 並插入 truncated marker。
- **理由**：兼顧除錯價值與儲存成本。

## Risks / Trade-offs

- 目前 probes 仍為 baseline，尚未接入實際 exporter。
- 權限/敏感資訊治理仍需與 Stage6 進一步整合。
- full restart playbook 依賴部署 service 命名一致性。

## Migration Plan

- 無資料遷移。
- 直接新增 Stage5 spec 與對應測試。
- 由 `openspec archive stage5-baseline` 歸檔 change。
