# coordinator-cli Specification

## Purpose
TBD - created by archiving change persona-phase2-coordinator-cli. Update Purpose after archive.
## Requirements
### Requirement: Job registry 持久化、確定性 job_id 且 corrupt fail-closed

`coordinator-cli` SHALL 提供 `JobRegistry(state_path=None, seq_start=0)`，支援 `create_job(task, persona, branch, pane, worktree)`、`list_jobs()`、`get_job(job_id)`、`update_status(job_id, status)`。每筆 job MUST 為 dict 並含 `job_id`、`task`、`persona`、`branch`、`pane`、`worktree`、`status`、`created_at`。`status` MUST ∈ `{dispatched, running, done, failed}`。job_id MUST **確定性**地由 task 與 registry 內部單調計數器推導為 `f"{task}-{seq}"`，MUST NOT 使用時間戳或亂數。registry 狀態 MUST 持久化為 JSON（預設路徑 `~/.agents/coordinator/jobs.json`，建構子可覆寫），mutating 操作後 MUST 落盤。讀取 corrupt／不可解析的狀態檔時 MUST raise（fail-closed），MUST NOT 靜默清空；狀態檔不存在時 MUST 視為空 registry。

#### Scenario: CRUD 與確定性 job_id

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.JobRegistryTests.test_create_get_update_deterministic_id -v`
- **THEN** 測試 MUST 驗證 `create_job` 回的 job 含確定性 `job_id`（如 `mytask-1`、同 task 再建得 `mytask-2`）、`status` 為 `dispatched`，且 `get_job` 可取回、`update_status` 能改為合法狀態

#### Scenario: 持久化 round-trip

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.JobRegistryTests.test_persistence_round_trip -v`
- **THEN** 測試 MUST 驗證一個 `JobRegistry` 寫入的 job，可由指向同一狀態檔的新 `JobRegistry` 經 `list_jobs`／`get_job` 讀回且欄位一致

#### Scenario: corrupt 狀態檔 fail-closed

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.JobRegistryTests.test_corrupt_state_fails_closed -v`
- **THEN** 測試 MUST 驗證以損壞（非法 JSON）狀態檔建構 `JobRegistry` 會 raise，MUST NOT 回傳空 registry 或靜默清空

### Requirement: 副作用 seam 為 Protocol 且真實作鏡射既有零件

`coordinator-cli` SHALL 以 `typing.Protocol` 定義 `PaneSender`（`send(pane_id: str, text: str) -> None`）與 `WorktreeCreator`（`create(branch: str) -> str`）。SHALL 提供真實作 `TmuxPaneSender`（鏡射 `daemon._send_to_pane`：`tmux send-keys -t <pane> -l <text>` 後 `tmux send-keys -t <pane> Enter`）與 `ScriptWorktreeCreator`（鏡射 `scripts/using-git-worktrees.sh` 的新分支路徑：`git worktree add -b <branch> <dir> <base>`，回 worktree 路徑）。真實作 MUST NOT 用於單元測試；單元測試 MUST 注入 fake，使得 import 本 package 不需要 tmux 或 git。

#### Scenario: Protocol 接受結構相容的 fake

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.SeamProtocolTests.test_fakes_satisfy_protocols -v`
- **THEN** 測試 MUST 驗證自訂的 fake PaneSender／fake WorktreeCreator（具相符 `send`／`create` 簽名）可被當作對應 Protocol 使用且其方法可被呼叫

### Requirement: Dispatcher 建 worktree、送命令、記 job 並可並行

`coordinator-cli` SHALL 提供 `Dispatcher(registry, pane_sender, worktree_creator)`，其 `dispatch(task, persona, pane_id, command)` MUST 依序：經 `worktree_creator` 建立該 job 的 worktree、經 `pane_sender` 將**呼叫者給定的 command 原字串**送入指定 pane、於 registry 記一筆 status 為 `dispatched` 的 job，並回傳該 job。worktree 建立失敗時 MUST NOT 送命令、MUST NOT 記 job（fail-closed）。`dispatch` MUST 支援連續多次呼叫產生多筆互不污染的 job（並行 fan-out，隔離靠 per-worktree／pane）。SHALL 提供 `poll_done(job_id, git_runner)`，當該 job 的 branch 出現新 commit（由可注入的 `git_runner` 判定）時 MUST 將 job 狀態更新為 `done`。

#### Scenario: dispatch 建 worktree、送確切命令、記 job

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.DispatcherTests.test_dispatch_records_job_and_sends_command -v`
- **THEN** 測試 MUST 以 fake PaneSender + fake WorktreeCreator 驗證 worktree 被建立、送入 pane 的文字等於給定 command、registry 記到一筆 `status=dispatched` 的 job 且回傳該 job

#### Scenario: 多次 dispatch 並行不互相污染

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.DispatcherTests.test_multiple_dispatch_isolated -v`
- **THEN** 測試 MUST 驗證連續兩次 `dispatch` 產生兩筆不同 `job_id` 的 job，各自綁定各自的 pane／worktree，`list_jobs` 同時可見

#### Scenario: poll_done 在 branch 有新 commit 時標記 done

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.DispatcherTests.test_poll_done_marks_done_on_new_commit -v`
- **THEN** 測試 MUST 以 fake git_runner（回傳異於 baseline 的 head）驗證 `poll_done` 將該 job 狀態更新為 `done`

### Requirement: Coordinator CLI 提供 dispatch/jobs/stat 且 main(argv) 可注入測試

`coordinator-cli` SHALL 提供 `python -m paulshaclaw.coordinator` 入口，含子命令 `dispatch --task T --persona R --pane %N --command "..."`、`jobs`、`stat <job_id>`。`dispatch` MUST 輸出新建 job 的 JSON，`jobs` MUST 輸出所有 job 的 JSON 清單，`stat <job_id>` MUST 輸出該 job 的 JSON（查無 job 時 MUST exit 非零）。`main(argv, *, registry=None, pane_sender=None, worktree_creator=None) -> int` MUST 在未注入時接線真實 seam，並 MUST 支援注入 registry／pane_sender／worktree_creator 以利測試（不啟動真 tmux／worktree）。

#### Scenario: dispatch 子命令以注入 fake 記 job

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.CliTests.test_main_dispatch_with_fakes -v`
- **THEN** 測試 MUST 以注入的 fake seam + 暫存 registry 驗證 `main(["dispatch", ...])` 回 0、送出的命令正確、registry 多一筆 job

#### Scenario: jobs 與 stat 子命令

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase2_coordinator_cli.CliTests.test_main_jobs_and_stat -v`
- **THEN** 測試 MUST 驗證 `main(["jobs"])` 列出既有 job、`main(["stat", <job_id>])` 對存在的 job 回 0、對不存在的 job_id 回非零退出碼

