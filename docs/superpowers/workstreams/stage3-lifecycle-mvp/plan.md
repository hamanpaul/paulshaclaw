# stage3-lifecycle-mvp / plan

## Scope

- Stage: 3（A 路線）
- 目標: 完成 artifact-first lifecycle MVP（schema + lifecycle.yaml + static gate）
- 先決依賴: Stage 1 baseline + Stage 2 baseline
- In scope: `paulshaclaw/lifecycle/`、`openspec/specs/stage3/`
- Out of scope: Stage 4 persona contract、Stage 6 security 引擎

## Steps

### Phase 1: Schema 基線
1. 定義 artifact frontmatter schema。
2. 建立 `lifecycle.yaml` template。

### Phase 2: Gate MVP
1. 建立 static gate check script。
2. 建立最小事件流（`requested/submitted/passed|failed`）。

### Phase 3: 回歸驗證
1. 建立 golden slice 測試案例。
2. 補 CI 或本地 runner 最小命令。

## Relevant files

- `openspec/specs/stage3/`
- `paulshaclaw/lifecycle/`
- `docs/research/03.stage3-lifecycle-slash-commands-artifacts-phase-gating-research.md`
- `docs/superpowers/workstreams/stage3-lifecycle-mvp/task.md`

## Verification

1. static gate script 可對 sample artifacts 給出一致結果。
2. golden slice 可完整跑過 phase 流程。
3. 事件流輸出可重放並回推當前狀態。

## Decisions

- MVP 先不依賴 daemon runtime，先確立檔案真相與 gate 行為。
