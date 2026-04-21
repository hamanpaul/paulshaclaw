## ADDED Requirements

### Requirement: Stage5 observability/recovery baseline requirement set

Stage5 MUST 定義 health report、`stage5.error.v1` error record、metrics 閾值草案、raw log 裁切規則，並在 `docs/ops/recovery.md` 提供 `tmux server crash` 與 `full runtime restart` 的可操作 playbook。

#### Scenario: Stage5 baseline tests pass with evidence

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage5_observability_recovery -v`
- **THEN** 測試 MUST 驗證 health/error/threshold/log policy/chaos matrix，且 red/green/final 證據存在於 `docs/superpowers/workstreams/stage5-observability-recovery/evidence/`

### Requirement: Stage5 Stage-boundary contract

Stage5 MUST consume Stage1 `/status` 與 Stage2 queue/janitor 健康訊號，不得在 Stage5 內修改 Stage1 啟動流程或 Stage2 治理路徑。Stage6 只可 consume Stage5 audit 索引，不得反向改 Stage5 指標定義。

#### Scenario: Stage5 workstream todo reflects boundary and handoff

- **WHEN** 審查者檢查 `docs/superpowers/workstreams/stage5-observability-recovery/todo.md`
- **THEN** `Handoff Notes` MUST 明確記載 Stage6 consume-only 邊界，且 blocker 狀態已更新為解除
