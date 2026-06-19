## Why

Stage 0 tooling foundation 已完成實作（tool-matrix、ref 規範、openspec+superpowers 骨架、worktree helper、regression harness），但當時 openspec change 流程尚未就緒，工作是直接在 worktree 上進行、未走 `propose → apply → archive`。後續 Stage 3 runtime 等變更需要對 Stage 0 基線做 diff、在 openspec workflow 下追加功能，因此必須把 Stage 0 現況事後追認為 baseline change，作為未來所有 Stage 0 範圍變更的唯一原點。

## What Changes

- 追認 `openspec/specs/stage0/tool-matrix.md` 為 tool refine baseline（6 個 rename target、Claude Code 支援狀態、sync-back gate 條件）
- 追認 `openspec/specs/stage0/ref-manifest.yaml` 為外部參考 repo pin baseline（custom-claw-tools / custom-skills / max / serialwrap / testpilot 五條 shallow clone）
- 追認 `scripts/using-git-worktrees.sh` 為 worktree / remote-tracking 管理 baseline（三段式 exit code、stale remote ref 自動清理）
- 追認 `scripts/sync-ref.sh` 為 ref manifest 驅動的 pin 同步 baseline
- 追認 `scripts/test-stage0-tooling-foundation.sh` 為 Stage 0 regression harness baseline（29 個檢查點，含 opsx prompt 雙源 drift check、遠端分支存在性、worktree helper 四條路徑）
- 追認 `openspec/specs/conventions/docs-layout.md` 為 docs 分工邊界 baseline（research / superpowers / openspec / ops 四者角色劃分）
- 追認 `.claude/commands/opsx/*.md` 與 `.github/prompts/opsx-*.prompt.md` 為 opsx slash-command 雙源 baseline（`opsx:new` / `opsx:ff` 骨架建立與 fleet-friendly 切分檢查）
- 追認 `AGENTS.md` / `CLAUDE.md` 為 agent workflow 入口；`CLAUDE.md` 以 symlink 指向 `AGENTS.md` 避免指令雙寫 drift
- 追認 `docs/superpowers/workstreams/stage0-tooling-foundation/{plan,task,todo,review}.md` 與 `evidence/*` 為 Stage 0 工作流程證據基線
- 無 **BREAKING**

## Capabilities

### New Capabilities

- `stage0-tooling`: Stage 0 的 tooling refine、外部參考 repo 管理、openspec + superpowers 骨架、worktree helper、regression harness 合約。本 capability 涵蓋 tool rename matrix、ref pin、opsx slash command 雙源、docs 分工邊界、workstream `plan/task/todo/evidence` 產物規範等全部 Stage 0 §8 驗收條目。

### Modified Capabilities

（無。Stage 0 為首次基線追認，沒有既有 capability 需要修改。）

## Impact

- **Code / Scripts**：
  - `scripts/using-git-worktrees.sh`、`scripts/sync-ref.sh`、`scripts/test-stage0-tooling-foundation.sh`
- **Specs**：
  - `openspec/specs/stage0/tool-matrix.md`、`openspec/specs/stage0/ref-manifest.yaml`、`openspec/specs/conventions/docs-layout.md`
- **Docs / Workflows**：
  - `AGENTS.md`、`CLAUDE.md`（symlink）
  - `.claude/commands/opsx/*.md`、`.github/prompts/opsx-*.prompt.md`
  - `docs/superpowers/workstreams/stage0-tooling-foundation/{plan,task,todo,review,evidence/*}`
- **Dependencies / 外部**：
  - `ref/` shallow clone 目錄（`.gitignore`，不進版控，但以 `openspec/specs/stage0/ref-manifest.yaml` 做 pin 控管）
- **Downstream stages**：
  - Stage 1 / 2 / 6 baseline change 以此為先決；Stage 3/4/5/7 的 runtime change 將以 Stage 0 capability 為 diff 原點。
