## Why

Stage 2 `paulsha-memory` 記憶治理基線已於 worktree `wt/stage2-paulsha-memory` 完成 spec/docs 實作（commit `79bf299` + fixup `6cc4356`），並於 commit `2da5ccb` 以 `--no-ff` 合併到 main。Stage 3 canonical contract v0.1 明確依賴 Stage 2 的「`inbox → work-centric → knowledge` 路由」、「importer / classifier / replay / janitor 邊界」、「`decayed / reactivation` 事件」以及「sync-back gate」四項語義；Stage 6 audit 也需要 Stage 2 artefact 的 provenance 欄位。本 change 以 reverse-record 方式把 Stage 2 已落地工作事後追認為 `stage2-memory-governance` capability，建立下游 Stage 3/4/6 change 的 diff 原點。

## What Changes

- 追認 `openspec/specs/stage2/scope.md` 為 Stage 2 scope baseline：角色邊界表、`inbox → work-centric → knowledge` 路由、`decayed/reactivation` 事件治理、janitor/replay 邊界、sync-back gate 五段 + Stage 3 frontmatter 必填欄位宣告
- 追認 `paulshaclaw/memory/routing.md` 為記憶路由 baseline（source→initial landing→upgrade 條件→target 四段表格）
- 追認 `paulshaclaw/janitor/service.md` 為 janitor 獨立服務 baseline（systemd 單位建議、reactivation 條件、與 replay 的不耦合宣告）
- 追認 `custom-skills/paulsha-memory/README.md` 為 sync-back staging scaffold baseline（5 條 sync-back gate 條件）
- 追認 `paulshaclaw/memory/tests/stage2_integration_check.sh` 為 Stage 2 integration 驗證 baseline（7 條 `require_text`：scope / routing / janitor / sync-back / frontmatter 欄位 / evidence 模板 / review 結論）
- 追認 `docs/superpowers/workstreams/stage2-paulsha-memory/{review.md,evidence/*}` 為 Stage 2 工作證據基線
- 無 **BREAKING**

## Capabilities

### New Capabilities

- `stage2-memory-governance`: Stage 2 的記憶路由、事件治理、janitor 邊界、sync-back gate、integration 驗證合約。本 capability 涵蓋 Stage 2 §8 驗收條目並對齊 Stage 3 canonical contract §2.6。

### Modified Capabilities

（無。Stage 2 為首次基線追認。）

## Impact

- **Specs**：
  - `openspec/specs/stage2/scope.md`
  - 新增 canonical `openspec/specs/stage2-memory-governance/spec.md`（archive 自動同步）
- **Docs / Design**：
  - `paulshaclaw/memory/routing.md`、`paulshaclaw/janitor/service.md`
  - `custom-skills/paulsha-memory/README.md`
- **Tests**：
  - `paulshaclaw/memory/tests/stage2_integration_check.sh`（7 條檢查）
- **Workstream 證據**：
  - `docs/superpowers/workstreams/stage2-paulsha-memory/{plan,task,todo,review}.md`
  - `docs/superpowers/workstreams/stage2-paulsha-memory/evidence/{README,stage2-integration-template}.md`
  - `docs/superpowers/archive/stage2-paulsha-memory-20260420T1855570800.md`
- **Downstream stages**：
  - Stage 3 lifecycle runtime 以 `decayed/reactivation` 事件與 frontmatter 欄位為 artifact 產出/消費 contract
  - Stage 6 audit 以 provenance/reference 欄位為 entry 來源
  - Stage 4 persona 以 replay bundle 為歷史輸入之一
