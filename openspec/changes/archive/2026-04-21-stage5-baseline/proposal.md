## Why

目前 Stage5 僅有 `openspec/specs/stage5/README.md` placeholder，缺少可驗收 Requirement/Scenario，導致 observability 與 recovery 相關交付（health probes、錯誤記錄、raw log policy、tmux/full restart playbook）無法以 OpenSpec 流程追溯。

## What Changes

- 建立 `stage5-baseline` OpenSpec change artifacts：`proposal.md`、`design.md`、`tasks.md`、`specs/stage5/spec.md`
- 補齊 Stage5 canonical spec，納入：
  - health probes 與健康報表輸出契約
  - `stage5.error.v1` 錯誤記錄格式
  - metrics 預設閾值草案
  - raw log retention/trim 規則
  - tmux crash / full restart playbook 與 chaos matrix 驗證
- 明確 Stage5 與相鄰 stage 邊界：
  - consume Stage1 `/status` 健康訊號
  - consume Stage2 queue/janitor backlog 訊號
  - Stage6 只 consume Stage5 audit 索引，不反向改 Stage5 指標定義
- 無 BREAKING 變更

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `stage5`: 從 placeholder 升級為可驗收 observability/recovery 規格。

## Impact

- **OpenSpec change artifacts**
  - `openspec/changes/stage5-baseline/proposal.md`
  - `openspec/changes/stage5-baseline/design.md`
  - `openspec/changes/stage5-baseline/tasks.md`
  - `openspec/changes/stage5-baseline/specs/stage5/spec.md`
- **Canonical Stage5 spec**
  - `openspec/specs/stage5/spec.md`
- **驗證入口**
  - `python3 -m unittest tests.test_stage5_observability_recovery -v`
  - `openspec validate stage5-baseline --strict`
