# stage5-observability-recovery / plan

## Scope

- Stage: 5
- 目標: 建立觀測、健康檢查、failover/recovery 基線
- 先決依賴: Stage 1 baseline + Stage 2 baseline
- In scope: `paulshaclaw/observability/`、`docs/ops/`
- Out of scope: Stage 3/4 contract 主檔修改

## Steps

### Phase 1: Metrics/Logs
1. 定義 health probes 與錯誤記錄格式。
2. 定義 log lifecycle 與保留策略。

### Phase 2: Recovery
1. 建立 tmux crash/full restart playbook。
2. 建立 daemon/memory pipeline 復原流程。

### Phase 3: 驗證
1. 建立 chaos/restart/recovery 測試。
2. 產出 recovery 證據。

## Relevant files

- `docs/ops/recovery.md`
- `paulshaclaw/observability/`
- `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`

## Verification

1. kill/restart 場景可恢復核心服務。
2. recovery 流程可重建最小可用狀態。
3. logs 與 errors 格式可供 Stage 6 審計索引。

## Decisions

- Dashboard 先採 federated 視圖，不新建 web UI。
