## 1. TDD RED（先寫失敗測試）

- [ ] 1.1 新增 `tests/test_persona_phase2_coordinator_cli.py`，`JobRegistryTests`：CRUD + 確定性 job_id（`task-1`/`task-2`）、持久化 round-trip（同狀態檔重載）、corrupt 狀態檔 fail-closed（raise）（`registry` 模組尚不存在 → RED）
- [ ] 1.2 同檔 `SeamProtocolTests`：自訂 fake PaneSender/WorktreeCreator 結構相容於 `seams.PaneSender`/`WorktreeCreator` Protocol 且方法可呼叫（`seams` 尚不存在 → RED）
- [ ] 1.3 同檔 `DispatcherTests`：以 fake seam 驗 dispatch 建 worktree + 送確切命令 + 記 job；多次 dispatch 並行不污染；`poll_done` 以 fake git_runner 標 done（`dispatcher` 尚不存在 → RED）
- [ ] 1.4 同檔 `CliTests`：`main(["dispatch", ...])`/`["jobs"]`/`["stat", id]` 以注入 fake + 暫存 registry 驗行為與退出碼（`cli` 尚不存在 → RED）
- [ ] 1.5 跑測試確認 RED 為「預期原因」（缺模組/缺屬性），捕捉輸出為證據

## 2. 實作 registry.py（job 持久化 + 確定性 id + fail-closed）

- [ ] 2.1 新增 `paulshaclaw/coordinator/registry.py`：`JobRegistry(state_path=None, seq_start=0)`，預設 `~/.agents/coordinator/jobs.json`；建構時讀檔（corrupt → raise；不存在 → 空），`_seq` 由載入 seq 還原
- [ ] 2.2 `create_job/list_jobs/get_job/update_status`：job_id=`f"{task}-{seq}"`（單調 seq，非時間/亂數），status ∈ `{dispatched,running,done,failed}`，每次 mutating 後原子 `_persist()`
- [ ] 2.3 RED → GREEN（`JobRegistryTests`）

## 3. 實作 seams.py（Protocol + 真實作，真實作不進測試）

- [ ] 3.1 新增 `paulshaclaw/coordinator/seams.py`：`PaneSender`（`send(pane_id, text) -> None`）、`WorktreeCreator`（`create(branch) -> str`）兩個 `typing.Protocol`（`runtime_checkable` 視需要）
- [ ] 3.2 真實作 `TmuxPaneSender`（鏡射 `daemon._send_to_pane`：`tmux send-keys -t <pane> -l <text>` + `Enter`，失敗 raise `ValueError`）、`ScriptWorktreeCreator`（`git worktree add -b <branch> <dir> <base>`，回路徑）；不在單元測試實體化
- [ ] 3.3 RED → GREEN（`SeamProtocolTests`，僅驗 fake 相容性 + 方法可呼叫，不碰真 tmux/git）

## 4. 實作 dispatcher.py（建 worktree→送命令→記 job + 完成偵測）

- [ ] 4.1 新增 `paulshaclaw/coordinator/dispatcher.py`：`Dispatcher(registry, pane_sender, worktree_creator)`，`dispatch(task, persona, pane_id, command)` 依序建 worktree→送 command→`registry.create_job(...)`(status=dispatched)→回 job；worktree 失敗則不送/不記（fail-closed）
- [ ] 4.2 `poll_done(job_id, git_runner)`：取 job branch，`git_runner` 回的 head 異於 job baseline → `update_status(...,"done")` 回更新後 job；相同 → 維持
- [ ] 4.3 RED → GREEN（`DispatcherTests`，含並行多 job 不污染）

## 5. 實作 cli.py + __main__.py（dispatch/jobs/stat，main(argv) 可注入）

- [ ] 5.1 新增 `paulshaclaw/coordinator/cli.py`：`main(argv=None, *, registry=None, pane_sender=None, worktree_creator=None) -> int`，argparse 子命令 `dispatch`(`--task/--persona/--pane/--command`)/`jobs`/`stat <job_id>`；未注入時接真實作，注入時用 fake
- [ ] 5.2 `dispatch` 印 job JSON、`jobs` 印 list JSON、`stat` 印單 job JSON（查無 → stderr + exit 1）；成功 exit 0
- [ ] 5.3 新增 `paulshaclaw/coordinator/__main__.py`：`sys.exit(cli.main())`
- [ ] 5.4 RED → GREEN（`CliTests`）

## 6. 匯出與不回歸

- [ ] 6.1 新增 `paulshaclaw/coordinator/__init__.py` 匯出 `registry`、`seams`、`dispatcher`、`cli`
- [ ] 6.2 確認 `core/daemon.py`、`core/config.py` 未被修改（scope 紀律；`git diff --name-only` 不含這兩檔）
- [ ] 6.3 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（忽略 2 個既知 stage11 textual 環境失敗 `query_one`）

## 7. 驗證

- [ ] 7.1 `openspec validate persona-phase2-coordinator-cli --strict` 通過
- [ ] 7.2 全程 local commit、不 push/不開 PR/不 merge（由 controller 在 gating 後處理）
