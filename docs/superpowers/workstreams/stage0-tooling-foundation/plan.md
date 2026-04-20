# stage0-tooling-foundation / plan

## Scope

- Stage: 0
- 目標: 完成前置工具命名校正、`ref/` 基線、`opsx:new`/`opsx:ff` 工作流骨架
- 先決依賴: 無
- In scope: `openspec/specs/stage0/`、`scripts/`、`config/worktrees/`、`docs/research/05...`
- Out of scope: `paulshaclaw/core/`、`paulshaclaw/memory/`、`paulshaclaw/lifecycle/` 內部實作

## Steps

### Phase 1: Baseline 同步
1. 更新 `ref-manifest.yaml` 與 `tool-matrix.md`。
2. 確認 `ops-companion` / `paulsha-memory` 命名一致。

### Phase 2: 骨架與規範
1. 維護 `opsx:new` 與 `opsx:ff` 指令文件。
2. 維護 `using-git-worktrees.sh` 與 worktree 對照表。

### Phase 3: 可驗證收斂
1. 產出 Stage 0 盤點與驗證證據。
2. 更新 shared 文件（僅 Stage 0 分支可改）。

## Relevant files

- `openspec/specs/stage0/ref-manifest.yaml`
- `openspec/specs/stage0/tool-matrix.md`
- `scripts/sync-ref.sh`
- `scripts/using-git-worktrees.sh`
- `config/worktrees/stage-worktrees.tsv`
- `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`

## Verification

1. `scripts/sync-ref.sh` 執行成功且可重建 `ref/MANIFEST.md`。
2. `openspec validate --specs` 可通過（或無可驗證項目時無錯誤）。
3. `docs/research/05...` 與 `tool-matrix.md` 的命名一致（`ops-companion`、`paulsha-memory`）。

## Decisions

- Stage 0 擁有 shared 規範檔的變更權。
- `ref/` 僅供閱讀/比對，不作 runtime 載入。
