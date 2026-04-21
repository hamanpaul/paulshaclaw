## 1. OpenSpec change artifacts（Spec/Doc 子線）

- [x] 1.1 完成 `proposal.md`，對齊 `docs/superpowers/workstreams/stage4-persona-contract/{plan,task,todo}.md`（驗證命令：`openspec status --change stage4-persona-contract --json`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/01-change-status.json`）
- [x] 1.2 完成 `design.md`，明確 Stage4 consume Stage3 phase/gate 的依賴邊界（驗證命令：`rg -n "consume|Stage3|phase|gate|不反向" openspec/changes/stage4-persona-contract/design.md`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/02-design-boundary-check.txt`）
- [x] 1.3 完成 change delta `specs/stage4/spec.md`，覆蓋 persona/handoff/guardrail/shadow-run requirement（驗證命令：`openspec validate stage4-persona-contract --strict`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/03-openspec-validate.txt`）

## 2. Persona contract / handoff / guardrail 可驗收條款

- [x] 2.1 新增 persona contract 三角色與 schema requirement（驗證命令：`python -m unittest tests.test_stage4_persona_contract.PersonaSchemaTests tests.test_stage4_persona_contract.RoleBaselineTests -v`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/11-persona-schema-tests.txt`）
- [x] 2.2 新增 `allowed_phases` 對齊 Stage3 vocabulary requirement（驗證命令：`python -m unittest tests.test_stage4_persona_contract.AllowedPhasesTests -v`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/12-allowed-phases-tests.txt`）
- [x] 2.3 新增 handoff message schema requirement（驗證命令：`python -m unittest tests.test_stage4_persona_contract.HandoffSchemaTests -v`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/13-handoff-schema-tests.txt`）
- [x] 2.4 新增 guardrail 越界拒絕 requirement（驗證命令：`python -m unittest tests.test_stage4_persona_contract.GuardrailTests -v`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/14-guardrail-tests.txt`）
- [x] 2.5 新增 shadow-run 驗證 requirement（驗證命令：`python -m unittest tests.test_stage4_persona_contract.ShadowRunTests -v`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/15-shadow-run-tests.txt`）

## 3. Canonical Stage4 spec 最小增量同步

- [x] 3.1 在 `openspec/specs/stage4/spec.md` 補上 Requirement/Scenario，不重寫 `README.md` 主體（驗證命令：`rg -n "^### Requirement:|^#### Scenario:" openspec/specs/stage4/spec.md`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/21-stage4-spec-structure.txt`）
- [x] 3.2 交叉確認 Stage4 對 Stage3 僅 consume phase/gate（驗證命令：`rg -n "consume|Stage3|MUST NOT|不反向" openspec/specs/stage4/spec.md openspec/changes/stage4-persona-contract/specs/stage4/spec.md`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/22-stage3-boundary-check.txt`）
- [x] 3.3 執行最終嚴格驗證（驗證命令：`openspec validate stage4-persona-contract --strict`；evidence：`docs/superpowers/workstreams/stage4-persona-contract/evidence/23-final-validate.txt`）
