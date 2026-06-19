## Why

設計 §3 的目標 pipeline 中，manager 對每個就緒 task **各開一個 worktree+pane** 並行 fan-out 跑整條 build pipeline（§9）。這個「派工原語」目前不存在：`core/daemon.py` 的 `LocalCoordinator` 只是個 counter stub（`create_job` 回 `local-N`、無持久化、無 worktree/pane 動作），CLAUDE.md 的 `[multi_agent_devflow]` / `[scope_violation]` 仍只是文字規則。設計 §7 要把它補成**真 job 管理 + 薄 CLI**，reuse 既有零件（`daemon._send_to_pane` 的 tmux send-keys、`scripts/using-git-worktrees.sh` 的 `git worktree add`、`core/config.py` 的 `CoordinatorSettings`）。

本 change 交付設計 §7 / §11 Phase 2 的 minimal coordinator CLI，為一個**自我封裝、可完整單元測試**的新 package `paulshaclaw/coordinator/`。所有副作用（tmux、git worktree、子程序）都藏在**可注入 seam** 之後，測試一律注入 fake，**不啟動真 copilot / 真 tmux / 真 worktree**。job_id **確定性**（由 task + 注入計數器推導），測試穩定。

## What Changes

- 新增 `paulshaclaw/coordinator/registry.py`：`JobRegistry(state_path=None, seq_start=0)`，CRUD `create_job(task, persona, branch, pane, worktree)` / `list_jobs()` / `get_job(job_id)` / `update_status(job_id, status)`。job 為 dict（`job_id`、`task`、`persona`、`branch`、`pane`、`worktree`、`status`、`created_at`）；`status` ∈ `{dispatched, running, done, failed}`。持久化為 JSON（預設 `~/.agents/coordinator/jobs.json`，建構子可覆寫）。**job_id 確定性**：`f"{task}-{seq}"`，seq 由 registry 內部單調計數器給（非時間／非亂數）。讀取 corrupt／不可解析狀態檔 **fail-closed（raise）**，呼應 loader / handoff 慣例。
- 新增 `paulshaclaw/coordinator/seams.py`：`typing.Protocol` `PaneSender`（`send(pane_id, text) -> None`）與 `WorktreeCreator`（`create(branch) -> str`，回 worktree 路徑）。真實作 `TmuxPaneSender`（`tmux send-keys -t <pane> -l <text>` + `Enter`，**鏡射** `daemon._send_to_pane`）、`ScriptWorktreeCreator`（呼 `git worktree add -b <branch> <dir> <base>`，**鏡射** `scripts/using-git-worktrees.sh` 的新分支路徑）。真實作**不**用於單元測試。
- 新增 `paulshaclaw/coordinator/dispatcher.py`：`Dispatcher(registry, pane_sender, worktree_creator)`，`dispatch(task, persona, pane_id, command)` 依序 **建 worktree → 送命令進 pane → registry 記一筆 job（status=dispatched）→ 回 job**。支援多 job 並行（隔離靠 per-worktree/pane，registry 多筆互不污染）。`poll_done(job_id, git_runner)`：當 job branch 出現新 commit（`git_runner` 為可注入 seam）即 `update_status(...,"done")`，否則維持。
- 新增 `paulshaclaw/coordinator/__main__.py` + `cli.py`：`python -m paulshaclaw.coordinator dispatch --task T --persona R --pane %N --command "..."`、`jobs`、`stat <job_id>`。`main(argv)` 預設接線真 seam，但所有 seam／registry 皆可由參數注入以利測試。
- 新增 `paulshaclaw/coordinator/__init__.py` 匯出 `registry` / `seams` / `dispatcher` / `cli`。
- 新增測試 `tests/test_persona_phase2_coordinator_cli.py`：registry CRUD + 持久化 round-trip + corrupt-file fail-closed；dispatcher 以 **FAKE** PaneSender + **FAKE** WorktreeCreator 斷言 job 記錄 + 送出的**確切命令** + worktree 建立；CLI `main(argv)` 以 fake 注入跑 dispatch/jobs/stat。全程 fake，無真 tmux/copilot/worktree。
- **本階段不動** `core/daemon.py`、`core/config.py`（scope 紀律）；不建 `persona-scope.yml`（Phase 3）；不接 frontmatter fan-out triage（Phase 4）。

## Capabilities

### New Capabilities

- `coordinator-cli`: minimal 多 agent 派工原語——job registry（確定性 job_id、JSON 持久化、corrupt fail-closed）、副作用 seam（PaneSender / WorktreeCreator Protocol + tmux / git-worktree 真實作）、dispatcher（建 worktree→送命令→記 job，可並行 fan-out，commit-based 完成偵測）、薄 CLI（`dispatch` / `jobs` / `stat`，`main(argv)` 可注入測試）。

### Modified Capabilities

<!-- 無；本 change 為新 capability，且刻意不改 core/daemon.py 的 LocalCoordinator（scope 紀律，留待後續 wiring 階段） -->

## Impact

- 代碼：新增 `paulshaclaw/coordinator/{__init__,registry,seams,dispatcher,cli,__main__}.py`；新增 `tests/test_persona_phase2_coordinator_cli.py`。
- 設計依據：`docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md` §3 / §7 / §9 / §11（Phase 2）/ §13。
- 實作計畫：`docs/superpowers/plans/2026-06-18-persona-phase2-coordinator-cli.md`。
- 無 runtime 行為變更（新 package 無既有消費者，CLI 為 opt-in）、無新增外部依賴（`tmux` / `git` 為既有前提，僅在真 seam 內呼叫、測試以 fake 旁路）；`core/daemon.py` 的 `LocalCoordinator` 維持不動。
