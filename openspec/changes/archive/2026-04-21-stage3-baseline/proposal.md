## Why

目前 `docs/superpowers/workstreams/stage3-lifecycle-mvp/` 與 `docs/research/03.stage3-lifecycle-slash-commands-artifacts-phase-gating-research.md` 已定義 Stage 3 MVP 方向（schema、`lifecycle.yaml`、static gate、events、golden slice），但尚未有對應 OpenSpec change artifact，導致 Stage 3 無法以 `openspec` 流程進行可追溯的 apply 與驗收。  
此外，現有 `openspec/specs/stage3/README.md` 屬契約敘述，缺少可直接驗收的 Requirement/Scenario 條款；Stage 3 與 Stage 1/2 的介面邊界雖有描述，但缺少明確測試入口。

## What Changes

- 建立 `stage3-lifecycle-mvp` change artifact 骨架：`proposal.md`、`design.md`、`tasks.md`、`specs/stage3/spec.md`。
- 將 Stage 3 MVP 收斂為可驗收條款：artifact frontmatter schema、`lifecycle.yaml` template、static gate、`requested/submitted/passed|failed` 事件流、golden slice 回歸。
- 明確化與 Stage 1 / Stage 2 的介面契約邊界：
  - Stage 1：只依賴 daemon `/status`、`/dispatch` 與 coordinator seam。
  - Stage 2：只透過 `inbox -> work-centric -> knowledge` 路徑消費，不由 Stage 3 直接寫 `knowledge` 或操作 janitor。
- 最小補強 canonical spec（`openspec/specs/stage3/**`）的可驗收條款，不重寫既有 README 契約內容。
- 無 **BREAKING** 變更。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `stage3`: 新增 Stage 3 lifecycle MVP 的可驗收 Requirement/Scenario，並補強 Stage 1/2 介面契約邊界與驗證命令/證據路徑。

## Impact

- **OpenSpec change artifacts**：
  - `openspec/changes/stage3-lifecycle-mvp/proposal.md`
  - `openspec/changes/stage3-lifecycle-mvp/design.md`
  - `openspec/changes/stage3-lifecycle-mvp/tasks.md`
  - `openspec/changes/stage3-lifecycle-mvp/specs/stage3/spec.md`
- **Canonical Stage 3 spec（最小增量）**：
  - `openspec/specs/stage3/spec.md`（新增可驗收條款）
- **驗證入口**（對齊 Stage 3 plan/task/todo）：
  - `openspec validate stage3-lifecycle-mvp --strict`
  - `python -m unittest tests.test_stage3_lifecycle_mvp -v`
- **Evidence 路徑約定**：
  - `docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/`
