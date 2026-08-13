---
type: change
scope: policy
---
policy engine 從 1.0.15 升版至 1.0.17（`.project-policy.yml`、`.github/workflows/policy-check.yml` 的 `uses:`／`policy_engine_ref` 雙鎖定 SHA 改為 `9e7fabbf0b5eea9ad933fa6798764b723934a0b7`、四份 agent 慣例檔 `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/`.github/copilot-instructions.md` 同步、內容位元組相同）。1.0.16／1.0.17 對下游 repo 未新增或變更任何規則，純為上游引擎自身的 distribution identity、runtime bundle 與 release workflow 修正；其中 1.0.16 引入的引擎版本 gate（執行中引擎版本與 repo 宣告的 `policy_version` 不符即 fail-loud）要求 pin SHA 與 `policy_version` 必須同 PR 原子更新，是本次同步的實益所在——版本對齊後，本機 `policy_check` 預檢才能與 CI 判定一致。本 repo `tests.yml` 已無條件執行 pytest（無 R-19 條件式 detect skeleton 需移除），故本次未涉及 workflow gate 結構調整。
