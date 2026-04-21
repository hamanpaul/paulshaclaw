## Why

目前 Stage4 只存在 `openspec/specs/stage4/README.md` placeholder，缺少可驗收 Requirement/Scenario，因此 persona contract、handoff schema、guardrail 與 shadow-run 驗證無法以 OpenSpec 流程追溯。為了讓 Stage4 能在不反向修改 Stage3 的前提下落地，需要建立 `stage4-persona-contract` change 並補齊 canonical spec 的最小可驗收條款。

## What Changes

- 建立 `stage4-persona-contract` OpenSpec change artifacts：`proposal.md`、`design.md`、`tasks.md`、`specs/stage4/spec.md`
- 將 Stage4 目標收斂為可驗收條款：
  - 三角色最小 contract（`manager`/`builder`/`reviewer`）
  - `allowed_phases` 與 Stage3 phase 名稱對應
  - handoff message schema（供 coordinator route 消費）
  - filesystem/tool guardrail 最小版本與拒絕案例
  - shadow-run 驗證流程
- 明確 Stage4 對 Stage3 的依賴邊界：只 consume Stage3 既有 phase vocabulary 與 gate output，不反向要求 Stage3 變更 lifecycle/runtime
- 補 canonical Stage4 spec（`openspec/specs/stage4/**`）最小增量 Requirement/Scenario
- 無 BREAKING 變更

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `stage4`: 將 Stage4 從 placeholder 補為可驗收的 persona contract / handoff / guardrail 規格，並明確 Stage3 依賴邊界（consume-only）。

## Impact

- **OpenSpec change artifacts**
  - `openspec/changes/stage4-persona-contract/proposal.md`
  - `openspec/changes/stage4-persona-contract/design.md`
  - `openspec/changes/stage4-persona-contract/tasks.md`
  - `openspec/changes/stage4-persona-contract/specs/stage4/spec.md`
- **Canonical Stage4 spec（最小增量）**
  - `openspec/specs/stage4/spec.md`
- **驗證入口（建議）**
  - `openspec validate stage4-persona-contract --strict`
  - `rg -n "Requirement:|Scenario:" openspec/specs/stage4/spec.md`
- **Evidence 路徑約定**
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/`
