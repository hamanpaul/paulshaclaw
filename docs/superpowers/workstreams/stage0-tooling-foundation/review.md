# stage0-tooling-foundation / review

## 範圍與符合度

- 已完成 `tool-matrix.md` refine PR / tracking 欄位補齊，並確認 `ref` pin 仍可由 GitHub commit API 解析。
- 已同步更新 `/opsx:new`、`/opsx:ff` 的 `.github` prompt 與 `.claude` command，要求寫入邊界、跨 stage 依賴、測試 gate、證據路徑，且檢查 remote tracking 一致性。
- 已更新 `scripts/using-git-worktrees.sh`，在 local branch 不存在時會對 `origin/<branch>` 做 live `ls-remote` 驗證、refresh stale remote-tracking ref，避免誤從 `BASE_REF` 建 branch。
- 已更新 `docs/research/05...` 與 workstream `plan/task/todo`，讓 Stage 0 規範、Relevant files、證據鏈與 checkbox 狀態一致。

## 風險與回歸檢查

- `using-git-worktrees.sh` 已覆蓋四條路徑：missing remote ref、stale remote-tracking ref、既有 local branch、無 local/remote 時從 `BASE_REF` 建新 branch。
- `.github/prompts/opsx-*.prompt.md` 與 `.claude/commands/opsx/*.md` 已加入等價檢查，降低雙份文件 drift。
- `ref` pin 維持原值；本輪只驗證 upstream commit 仍存在，未進行版本升級。

## 測試與證據

- Red: `evidence/01-red-test-stage0-tooling-foundation.txt`、`evidence/09-red-handoff-plan-sync.txt`、`evidence/11-red-review-fixes.txt`、`evidence/13-red-stale-remote-ref.txt`
- Green / Refactor: `evidence/08-pristine-test-stage0-tooling-foundation.txt`、`evidence/10-green-handoff-plan-sync.txt`、`evidence/12-green-review-fixes.txt`、`evidence/14-green-stale-remote-ref.txt`、`evidence/15-final-regression.txt`
- 其他驗證：`evidence/06-ref-pin-check.txt`、`evidence/07-sync-ref.txt`、`evidence/16-final-openspec-validate.txt`

## Code review 結論

- `superpowers:code-reviewer` 最終結論：**Ready**
- Critical issues：無
- Important issues：無
- Minor issues：測試樣板中的 `trap ... RETURN` 可在未來抽 helper 以降低重複；不影響本次合併

## 未解風險

- 目前 `tool-matrix.md` 的 tracking 欄位仍是規劃型追蹤，後續真正開 PR 時需把對應條目拆回各 stage/workstream 的執行待辦。
