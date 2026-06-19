> Stage 0 baseline 為 reverse-record change：Stage 0 本體已於 commit `7ac043b` 合併至 main。以下任務均為「對照已落地工作驗證 spec 成立」的反向檢核，不是前向實作。

## 1. Tool rename & reference baseline

- [x] 1.1 確認 `openspec/specs/stage0/tool-matrix.md` 的 B 區六個 rename target 欄位齊備，D 區 sync-back gate 條款存在
- [x] 1.2 確認 `openspec/specs/stage0/ref-manifest.yaml` 包含 `custom-claw-tools / custom-skills / max / serialwrap / testpilot` 五個 repo，且 `policy.tracked_in_git=false`、`policy.runtime_source=false`

## 2. Scripts baseline

- [x] 2.1 確認 `scripts/using-git-worktrees.sh` 的四條路徑（missing remote / stale ref / local existing / new branch）與對應 exit code 已實作
- [x] 2.2 確認 `scripts/sync-ref.sh` 以 `ref-manifest.yaml` 為輸入、對每個 repo 做 shallow clone 到宣告的 `path`
- [x] 2.3 確認 `scripts/test-stage0-tooling-foundation.sh` 存在且現場執行全部 29 條檢查結果為 PASS（證據：`docs/superpowers/workstreams/stage0-tooling-foundation/evidence/`）

## 3. Conventions & entry-points baseline

- [x] 3.1 確認 `openspec/specs/conventions/docs-layout.md` 列出 research / superpowers/specs / superpowers/plans / superpowers/workstreams / ops / openspec/specs / openspec/changes 七個角色
- [x] 3.2 確認 `.claude/commands/opsx/` 與 `.github/prompts/` 皆有 `opsx:new`、`opsx:ff` 定義；body 無 drift（由 §2.3 harness 檢查覆蓋）
- [x] 3.3 確認 `CLAUDE.md` 是 symlink 指向 `AGENTS.md`（`readlink CLAUDE.md` 回傳 `AGENTS.md`）

## 4. Workstream artefact baseline

- [x] 4.1 確認 `docs/superpowers/workstreams/stage0-tooling-foundation/` 具備 `plan.md`、`task.md`、`todo.md`、非空 `evidence/`
- [x] 4.2 確認 `plan.md` 包含 `## Scope / ## Steps / ## Relevant files / ## Verification / ## Decisions` 五段
- [x] 4.3 確認 `todo.md` 包含 `## Current Sprint / ## Blockers / ## Evidence / Links / ## Handoff Notes` 四段

## 5. Archive readiness

- [x] 5.1 以 `openspec status --change stage0-baseline` 確認所有 artifact 狀態為 done
- [x] 5.2 以 `/opsx:archive stage0-baseline` 將 change 封檔、同步 delta spec 至 `openspec/specs/stage0-tooling/`
