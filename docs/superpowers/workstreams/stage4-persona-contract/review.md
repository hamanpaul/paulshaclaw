# stage4-persona-contract / review

## Scope

- `paulshaclaw/persona/contract.py`
- `paulshaclaw/persona/guardrail.py`
- `paulshaclaw/persona/context.py`
- `paulshaclaw/persona/shadow.py`
- `tests/test_stage4_persona_contract.py`
- `openspec/changes/stage4-persona-contract/*`
- `openspec/specs/stage4/spec.md`

## 規格符合度

| 項目 | 結果 | 備註 |
|---|---|---|
| 三角色 contract（manager/builder/reviewer） | 通過 | 含最小 role/version/summary/allowed_phases/write_paths/allowed_tools |
| `allowed_phases` 與 Stage3 phase 對齊 | 通過 | 以 Stage3 canonical phase vocabulary 驗證子集合 |
| handoff schema | 通過 | 必填含 `gate_status`，並驗證 phase/gate 相容 |
| filesystem/tool guardrail | 通過 | fail-closed 拒絕越界請求並回傳原因 |
| user overlay 載入點 | 通過 | `load_user_overlay` + `build_persona_context` 已落地 |
| shadow-run 驗證流程 | 通過 | `run_shadow_validation` 回傳 role/phase/gate/guardrail 決策摘要 |
| OpenSpec change 與 canonical spec | 通過 | change strict validate 成功，stage4 spec 已有 Requirement/Scenario |

## 測試與驗證

執行命令：

```bash
python3 -m unittest tests.test_stage4_persona_contract -v
python3 -m unittest discover -s tests -v
openspec validate stage4-persona-contract --strict
openspec validate --specs
```

結果：

- `tests.test_stage4_persona_contract`：10 tests 全通過
- `tests` 全量：38 tests 全通過
- `openspec validate stage4-persona-contract --strict`：valid
- `openspec validate --specs`：6 passed, 0 failed

對應 evidence：

- `docs/superpowers/workstreams/stage4-persona-contract/evidence/20260421-red-unittest.txt`
- `docs/superpowers/workstreams/stage4-persona-contract/evidence/20260421-green-unittest.txt`
- `docs/superpowers/workstreams/stage4-persona-contract/evidence/20260421-final-unittest-discover.txt`
- `docs/superpowers/workstreams/stage4-persona-contract/evidence/01-change-status.json`
- `docs/superpowers/workstreams/stage4-persona-contract/evidence/03-openspec-validate.txt`
- `docs/superpowers/workstreams/stage4-persona-contract/evidence/23-final-validate.txt`

## Code Review 結論

- Verdict: `approve`
- 結論：Stage4 最小 contract/handoff/guardrail/shadow-run 已可驗證交付，且維持 Stage3 consume-only 邊界。

## 未解風險

1. `personas.yaml` 目前尚未接實體檔案載入流程，現階段以程式內 catalog 為基線。
2. filesystem guardrail 仍是 pattern 比對 MVP，尚未含 realpath/symlink 強化。
3. tool allowlist 仍是字串前綴比對，未涵蓋 alias/wrapper 命令繞過。
