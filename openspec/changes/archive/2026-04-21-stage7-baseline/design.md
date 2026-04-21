## Context

Stage7 需要在不破壞既有 runtime 的前提下，先落地可驗證的三分部署規格。現有 workstream 文件已列出 install/upgrade/uninstall、permission、rollback 任務，但 OpenSpec 尚未形成可驗收條款。

## Goals / Non-Goals

**Goals:**
- 建立可測試的 deployment planning baseline。
- 固定 template rename 與目標路徑規則。
- 對 state/secret 權限採 fail-closed。
- 定義 secret install 最小互動步驟與 checkpoint。
- 為 install/upgrade/uninstall 建立 rollback baseline。

**Non-Goals:**
- 不執行真實檔案部署與 systemd 操作。
- 不引入 Stage8/Stage10 的成本治理與 protocol 演進。
- 不修改 Stage5 `docs/ops/recovery.md`。

## Decisions

### Decision 1：命令只輸出 JSON plan

- **選擇**：`python -m paulshaclaw.deploy <command>` 先輸出可審查 plan，不直接套用。
- **理由**：降低破壞風險，符合 baseline 階段目標。

### Decision 2：template rename 固定 `__INSTANCE__` + `.tmpl` 移除

- **選擇**：統一 rename 規則，避免不同 plane 各自實作。
- **理由**：便於測試與後續擴充。

### Decision 3：state/secret 權限 fail-closed

- **選擇**：`state` 拒絕 group writable/other 權限；`secret` 限制 owner-only。
- **理由**：先建最小安全基線，後續再擴充 owner/ACL/symlink hardening。

## Risks / Trade-offs

- 目前 rollback 為規劃層，尚未有真實 artifact restore 流程。
- 權限檢查目前只看 mode bits。
- secret 流程尚未串接 Stage6 approval/audit。

## Migration Plan

- 無資料遷移。
- 新增 `paulshaclaw/deploy/` 模組與測試。
- 由 `openspec archive stage7-baseline` 歸檔 change。
