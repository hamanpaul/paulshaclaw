## 1. OpenSpec change 骨架與契約對齊

- [x] 1.1 完成 `proposal.md`，對齊 `docs/superpowers/workstreams/stage3-lifecycle-mvp/{plan,task,todo}.md` 與 `docs/research/03.stage3-lifecycle-slash-commands-artifacts-phase-gating-research.md`（驗證命令：`openspec status --change stage3-lifecycle-mvp --json`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/01-change-status.json`）
- [x] 1.2 完成 `design.md`，明確 Stage 1 daemon/coordinator seam 與 Stage 2 memory routing/janitor 邊界（驗證命令：`rg -n "Stage 1|Stage 2|/dispatch|create_job|inbox -> work-centric -> knowledge|janitor" openspec/changes/stage3-lifecycle-mvp/design.md`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/02-design-boundary-check.txt`）
- [x] 1.3 完成 change delta `specs/stage3/spec.md`（驗證命令：`openspec validate stage3-lifecycle-mvp --strict`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/03-openspec-validate.txt`）

## 2. Stage 3 MVP 可驗收條款

- [x] 2.1 新增/補強 frontmatter schema 與 `lifecycle.yaml` template requirement（驗證命令：`python -m unittest tests.test_stage3_lifecycle_mvp.FrontmatterSchemaTests tests.test_stage3_lifecycle_mvp.LifecycleTemplateTests -v`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/11-schema-template-tests.txt`）
- [x] 2.2 新增/補強 static gate 與最小事件流 requirement（驗證命令：`python -m unittest tests.test_stage3_lifecycle_mvp.EventReplayTests -v`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/12-event-replay-tests.txt`）
- [x] 2.3 新增/補強 golden slice 七階段回歸 requirement（驗證命令：`python -m unittest tests.test_stage3_lifecycle_mvp.GoldenSliceTests -v`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/13-golden-slice-tests.txt`）

## 3. Canonical Stage 3 spec 最小補強

- [x] 3.1 在 `openspec/specs/stage3/spec.md` 補上 Requirement/Scenario 可驗收條款，不重寫 `README.md` 主體契約（驗證命令：`rg -n "^### Requirement:|^#### Scenario:" openspec/specs/stage3/spec.md`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/21-stage3-spec-structure.txt`）
- [x] 3.2 交叉確認 Stage 1/2 契約邊界在 canonical Stage 3 spec 有明確條款（驗證命令：`rg -n "Stage 1|Stage 2|/status|/dispatch|inbox -> work-centric -> knowledge|knowledge/\\*" openspec/specs/stage3/spec.md`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/22-stage-boundary-contract.txt`）
- [x] 3.3 執行 change 最終嚴格驗證（驗證命令：`openspec validate stage3-lifecycle-mvp --strict`；evidence：`docs/superpowers/workstreams/stage3-lifecycle-mvp/evidence/23-final-validate.txt`）
