## ADDED Requirements

### Requirement: coordinator backend selection
bot 啟動路徑 SHALL 依 `coordinator.backend` 設定（env 覆寫 `PSC_COORDINATOR_BACKEND`）選擇 coordinator：未設定 → 維持 `UnavailableCoordinator`（fail-closed，現行為不變）；`"control"` → `ControlPlaneCoordinator`（create_job 寫 dispatch request 並即回 req_id）；`LocalCoordinator` SHALL 標記 test-only 且不得被 production selection 選中。

#### Scenario: 未設定維持 fail-closed
- **WHEN** config 無 backend 且 env 未設
- **THEN** `/dispatch` 回覆「coordinator backend 未設定」，不產生假 job id（現行測試零回歸）

#### Scenario: control backend 產真 job
- **WHEN** backend 設 `"control"` 且 manager daemon 運行中
- **THEN** `/dispatch <slice>` 寫出合法 dispatch request、回覆含 req_id；job_id 隨 done 紀錄可查
