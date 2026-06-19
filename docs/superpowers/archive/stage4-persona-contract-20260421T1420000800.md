# stage4-persona-contract archive

## scope

- Stage 4 最小可驗證切片：persona contract、allowed_phases、handoff schema、filesystem/tool guardrail、user overlay 載入點、shadow-run 驗證。
- OpenSpec change：`stage4-persona-contract`（proposal/design/tasks/spec delta）。
- canonical spec：`openspec/specs/stage4/spec.md`。

## 實作摘要

1. 新增 `paulshaclaw/persona/` 模組：
   - `contract.py`：三角色 contract、schema 驗證、handoff 驗證
   - `guardrail.py`：filesystem/tool fail-closed 決策
   - `context.py`：user overlay 載入與 persona context 組裝
   - `shadow.py`：shadow-run 驗證摘要輸出
2. 新增 `tests/test_stage4_persona_contract.py`，覆蓋 schema/phase/handoff/guardrail/shadow-run。
3. 建立 OpenSpec change `openspec/changes/stage4-persona-contract/`，並同步 canonical `openspec/specs/stage4/spec.md`。
4. 補齊 Stage4 workstream 的 task/todo/review/evidence。

## 測試證據

- Red：
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/20260421-red-unittest.txt`
- Green / Regression：
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/20260421-green-unittest.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/20260421-final-unittest-discover.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/11-persona-schema-tests.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/12-allowed-phases-tests.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/13-handoff-schema-tests.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/14-guardrail-tests.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/15-shadow-run-tests.txt`
- OpenSpec：
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/01-change-status.json`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/03-openspec-validate.txt`
  - `docs/superpowers/workstreams/stage4-persona-contract/evidence/23-final-validate.txt`

## review 結論

- `docs/superpowers/workstreams/stage4-persona-contract/review.md`
- verdict：`approve`

## 未解風險

1. `personas.yaml` 尚未接入實體檔載入與版本遷移策略。
2. guardrail 尚未加入 realpath/symlink 層級硬化。
3. allowlist/phase 契約如 Stage3 未來變更，需 follow-up 更新 Stage4 consume 規格。
