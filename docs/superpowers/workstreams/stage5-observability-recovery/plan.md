# stage5-observability-recovery / plan

## Scope

- Stage: 5
- 目標: 建立 observability、health probes、raw log lifecycle 與 recovery 基線
- 先決依賴: Stage 1 baseline + Stage 2 baseline
- In scope: `paulshaclaw/observability/`、`docs/ops/`、`openspec/specs/stage5/`
- Out of scope: Stage 3/4 contract 主檔修改

## Steps

### Phase 1: Metrics/Logs
1. 定義 health probes 與錯誤記錄格式。
2. 定義 metrics 預設閾值與 raw log lifecycle / 保留策略。

### Phase 2: Recovery
1. 建立 tmux crash/full restart playbook。
2. 建立 daemon/memory pipeline 復原流程。

### Phase 3: 驗證
1. 以 TDD 建立 Stage5 單元測試（先 red 後 green）。
2. 產出 chaos/restart/recovery matrix 與 final regression 證據。

## Relevant files

- `docs/ops/recovery.md`
- `paulshaclaw/observability/`
- `openspec/specs/stage5/spec.md`
- `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`

## Verification

1. `python3 -m unittest tests.test_stage5_observability_recovery -v` 先失敗再通過。
2. `python3 -m unittest discover -s tests` 全量通過。
3. health report、error record、raw log policy 與 chaos matrix 可供 Stage 6 審計索引與後續接線。

## Decisions

- Dashboard / UI 先不做；本輪只固化資料結構、playbook 與 evidence。
