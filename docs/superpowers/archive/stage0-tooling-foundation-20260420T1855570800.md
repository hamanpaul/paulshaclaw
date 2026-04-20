# stage0-tooling-foundation archive

## scope

- workstream：`stage0-tooling-foundation`
- sprint 範圍：補齊 Stage 0 tooling foundation 的 Current Sprint 與 task 清單
- 主要檔案：`openspec/specs/stage0/tool-matrix.md`、`scripts/using-git-worktrees.sh`、`/opsx:new`、`/opsx:ff` 文件、`docs/research/05...`、workstream `plan/task/todo`

## 實作摘要

1. 補齊 `tool-matrix.md` 的 `refine PR / tracking` 欄位，移除 `TBD` 並標示各項前置條件。
2. 更新 `.github` / `.claude` 的 `/opsx:new`、`/opsx:ff` 文件，要求寫入邊界、測試 gate、證據路徑與 remote tracking 一致性。
3. 強化 `scripts/using-git-worktrees.sh`：local branch 優先，其次 live 檢查 `origin/<branch>`、refresh stale remote-tracking ref，最後才從 `BASE_REF` 建新 branch。
4. 新增 `scripts/test-stage0-tooling-foundation.sh`，以 TDD 驗證 tool-matrix、Stage 0 規範、prompt/command 等價性與 worktree 四條分支路徑。
5. 更新 Stage 0 research 與 workstream 文件，補齊 Relevant files、證據鏈與 checkbox 狀態。

## 測試證據

- Red：
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/01-red-test-stage0-tooling-foundation.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/09-red-handoff-plan-sync.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/11-red-review-fixes.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/13-red-stale-remote-ref.txt`
- Green / Refactor：
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/10-green-handoff-plan-sync.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/12-green-review-fixes.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/14-green-stale-remote-ref.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/15-final-regression.txt`
- 補充驗證：
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/06-ref-pin-check.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/07-sync-ref.txt`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/evidence/16-final-openspec-validate.txt`

## review 結論

- `superpowers:code-reviewer` 最終結論：**Ready**
- Critical / Important issues：無
- Minor：測試樣板仍有可抽 helper 的重複，但不影響本次交付

## 未解風險

- `tool-matrix.md` 的 tracking 欄位目前仍屬規劃性清單，真正進入跨 repo refine 時，仍需拆解成對應 repo / stage 的執行待辦與 PR 追蹤。
