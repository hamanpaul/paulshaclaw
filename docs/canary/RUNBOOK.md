# Phase D Canary Runbook（#123）

trivial 有界 `dispatch:auto` slice 端到端跑一輪，shadow 觀測 dispatch→headless→完成偵測→manifest。本機 log 觀測（relay→Telegram 留 #120）。

## 前置
- headless CLI 可用：`command -v claude codex copilot`。
- 在 repo 根、分支 `feature/123-phase-d-canary`。
- `--allow-unsafe`（headless 自主必需）；canary 任務有界（見 `canary.plan.md`），agent 跑 `feature/canary-*` worktree 隔離。

## 程序（依序，非並行）

```bash
# claude（預設 model）
python -m paulshaclaw.coordinator tick --specs-dir docs/canary/claude  --executor claude  --allow-unsafe
# codex（預設 model）
python -m paulshaclaw.coordinator tick --specs-dir docs/canary/codex   --executor codex   --allow-unsafe
# copilot（claude-haiku-4.5 測試）
python -m paulshaclaw.coordinator tick --specs-dir docs/canary/copilot --executor copilot --allow-unsafe --model claude-haiku-4.5
```

每家：`tick` 先 fanout（建 worktree + headless 啟動，記 job pid/log），再 complete（poll）。headless agent 為背景進程，通常需再跑 `tick`/`complete` 幾趟讓 `poll_headless_done` 偵測完成：

```bash
python -m paulshaclaw.coordinator complete --handoff-dir runtime/handoff   # 重複到 manifest 出現
cat runtime/handoff/canary-claude.json    # 觀測：gate_status / completion / exit_code
```

## 觀測點
- worktree：`git worktree list | grep canary`
- job：`python -m paulshaclaw.coordinator jobs`
- log/JSONL：job 的 `log_path`（末筆 result）；exit sentinel：`<log_dir>/<slice>.exit`
- manifest：`runtime/handoff/canary-<e>.json`（`gate_status==passed` 即完成側走通）

## 清理
```bash
git worktree remove --force .../feature/canary-<e>   # 各 canary worktree
rm -rf runtime/dispatch/canary-* runtime/handoff/canary-*.json
```
確認主工作樹/主分支未被動（`git status`、`git log main -1`）。

## 結果
彙整三家 pass/fail（含原因）、耗時、manifest 到 `docs/canary/RESULTS.md` 或 PR body。
