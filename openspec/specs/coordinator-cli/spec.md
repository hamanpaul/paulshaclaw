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

### Requirement: Autonomy frontmatter 解析預設 HOLD 且支援 depends_on

`coordinator-cli` SHALL 提供 `paulshaclaw/coordinator/autonomy.py`，其 `parse_spec_frontmatter(path) -> dict` MUST 以 PyYAML（`safe_load`）解析 superpowers spec 開頭的 `---` frontmatter 區塊，回傳含 `dispatch`、`slice_id`、`plan`、`depends_on`、`path` 鍵的 dict。`dispatch` MUST 僅在 frontmatter 明確為字面值 `auto` 時為 `'auto'`，其餘所有情況（缺 `dispatch` key、值非 `auto`、無合法 frontmatter、檔案不以 `---` 起頭）MUST 預設為 `'hold'`（硬安全要求：未明確宣告即不自主派工）。`slice_id` 與 `plan` 缺省 MUST 為 `None`；`depends_on` 缺省或非 list MUST 為 `[]`（單一字串值 MAY 容錯為單元素 list）。`parse_spec_frontmatter` MUST 容忍完全無 frontmatter 的檔案而不 raise（視為 hold）。

#### Scenario: dispatch:auto 帶 slice_id/plan/depends_on 被正確解析

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests.test_parse_auto_with_depends_on -v`
- **THEN** 測試 MUST 驗證一份 frontmatter 含 `dispatch: auto`、`slice_id`、`plan`、`depends_on: [a, b]` 的 spec 被解析為 `dispatch=='auto'`、對應的 `slice_id`/`plan`、`depends_on==['a','b']`

#### Scenario: 缺 dispatch 或值非 auto 預設 hold

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests.test_parse_hold_and_default -v`
- **THEN** 測試 MUST 驗證 `dispatch: hold`、拼錯的 dispatch 值、以及無 `dispatch` key 三種 frontmatter 皆解析為 `dispatch=='hold'`，且 `depends_on` 缺省為 `[]`

#### Scenario: 無 frontmatter 的 spec 視為 hold 不 raise

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests.test_parse_missing_frontmatter_is_hold -v`
- **THEN** 測試 MUST 驗證一份不以 `---` 起頭（無 frontmatter）的 markdown 被解析為 `dispatch=='hold'`、`slice_id is None`、`depends_on==[]`，且 `parse_spec_frontmatter` MUST NOT raise

### Requirement: scan_specs 確定性掃描 spec 目錄

`coordinator-cli` 的 `autonomy.scan_specs(specs_dir) -> list[dict]` MUST 掃描 `specs_dir` 下的 `*.md`，對每檔呼叫 `parse_spec_frontmatter`，回傳各 meta 的清單（每筆含 `path`）。輸出順序 MUST 確定性（依路徑排序）。`specs_dir` 不存在時 MUST 回傳空清單，MUST NOT raise。

#### Scenario: 掃描目錄回確定性排序的 metas

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ScanTests.test_scan_specs_deterministic -v`
- **THEN** 測試 MUST 以暫存目錄放數份 spec，驗證 `scan_specs` 回的 meta 數量與檔案數一致、含各自 `path`、且順序為路徑排序（確定性）

### Requirement: depends_on 循環相依偵測並 refuse

`coordinator-cli` 的 `autonomy.detect_cycles(metas)` MUST 以各 meta 的 `slice_id` 為節點、`depends_on` 為有向邊建圖，當存在循環相依時 MUST raise `ValueError`（refuse，不派工）。指向不存在於 metas 的 `slice_id` 的 `depends_on` MUST NOT 被視為循環（交由 `is_satisfied` 判定其滿足與否）。`ready_units` MUST 在計算就緒集前先呼叫 `detect_cycles`，使有環時整批拒絕、不釋放任何單位。建圖時若偵測到**重複的 `slice_id`**（兩筆以上 meta 共用同一 `slice_id`，身分不明確），MUST 在 DFS 前 raise `ValueError`（refuse）：靜默以後者覆寫前者的 `depends_on` 邊會遮蔽真環，且下游 fan-out 會對同一 `feature/<slice_id>` 重複派工（違反「一單位一 job」）。

#### Scenario: 直接與間接循環相依 raise

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CycleTests.test_detect_cycle_raises -v`
- **THEN** 測試 MUST 驗證直接環（A→B→A）與間接環（A→B→C→A）的 metas 使 `detect_cycles` raise `ValueError`，且非環圖（A→B、C→B）MUST NOT raise

#### Scenario: 重複 slice_id 直接 refuse 且不遮蔽真環

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CycleTests.test_duplicate_slice_id_refused tests.test_persona_phase4_fanout_autonomy.CycleTests.test_duplicate_slice_id_does_not_mask_cycle -v`
- **THEN** 測試 MUST 驗證兩筆共用同一 `slice_id` 的 metas 使 `detect_cycles`／`ready_units` raise `ValueError`（訊息含「重複 slice_id」），且 `[A→B, A→[], B→A]`（第二個 A 試圖覆寫 A→B）仍 MUST raise（不得因覆寫而漏掉 A↔B 真環）

#### Scenario: ready_units 在有環時整批拒絕

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CycleTests.test_ready_units_refuses_on_cycle -v`
- **THEN** 測試 MUST 驗證對含循環相依的 metas 呼叫 `ready_units(metas, is_satisfied)` 會 raise `ValueError`（先 `detect_cycles`），MUST NOT 回傳部分就緒集

### Requirement: ready_units 三條件就緒判定且 is_satisfied 可注入

`coordinator-cli` 的 `autonomy.ready_units(metas, is_satisfied)` MUST 回傳同時滿足下列條件的 metas：`slice_id` 為非空字串（有身分）、`dispatch == 'auto'`、`plan` 為非空字串、且每個 `depends_on` 經注入的 `is_satisfied(slice_id) -> bool` 皆為真（`depends_on` 為空時自然滿足）。`slice_id` 為 `None`／非字串／空字串的單位無身分（無法成為 `depends_on` 目標、無法被追蹤或交接），依 fail-safe 立場 MUST NOT 就緒。`is_satisfied` MUST 為可注入參數（呼叫者決定相依「滿足」的判定來源，例 merged-to-main 或 handoff `gate_status`）。`coordinator-cli` SHALL 另提供預設 `default_is_satisfied(slice_id, handoff_dir='runtime/handoff') -> bool`（讀 `<handoff_dir>/<slice_id>.json` 且 `gate_status == 'passed'` → True，否則 False；檔不存在/壞檔 → False，fail-closed），但 `ready_units`/`dispatch_ready` MUST 不寫死此來源、一律收注入 predicate。輸出順序 MUST 確定性。

#### Scenario: 預設 hold 的單位不就緒

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_hold_not_ready -v`
- **THEN** 測試 MUST 驗證一個 `dispatch=='hold'`（或無 plan）的 meta 不出現在 `ready_units` 結果中，即使其 `depends_on` 全滿足

#### Scenario: depends_on 未滿足不就緒、滿足才就緒

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_depends_on_gates_readiness -v`
- **THEN** 測試 MUST 以注入的 fake `is_satisfied` 驗證：當某 `depends_on` 回 False 時該 auto+plan 單位不就緒；當 `is_satisfied` 對所有相依回 True 時該單位就緒；`depends_on` 為空的 auto+plan 單位恆就緒

#### Scenario: 無 slice_id 的單位不就緒

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_no_slice_id_not_ready -v`
- **THEN** 測試 MUST 驗證 `dispatch=='auto'` 且有 `plan` 但 `slice_id` 為 `None`／空字串的 meta 不出現在 `ready_units` 結果中（無身分 → fail-safe 不就緒）

#### Scenario: default_is_satisfied 讀 handoff gate_status

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_default_is_satisfied_reads_gate_status -v`
- **THEN** 測試 MUST 以暫存 handoff 目錄驗證 `default_is_satisfied` 對 `gate_status=='passed'` 的 manifest 回 True、對非 passed 或不存在的 manifest 回 False

### Requirement: fan-out reuse Phase 2 Dispatcher 派出就緒集

`coordinator-cli` 的 `autonomy.dispatch_ready(metas, is_satisfied, dispatcher, persona='builder', git_runner=None) -> list` MUST 先以 `ready_units(metas, is_satisfied)` 算出就緒集，再對每個就緒單位經注入的 `dispatcher`（Phase 2 `Dispatcher`）呼叫 `dispatch(...)` 各派一筆 job（一單位一 job；隔離靠 per-worktree／pane，故並行安全），並回傳 dispatched jobs 清單。`dispatch_ready` MUST NOT 重新實作 dispatch/registry 邏輯（reuse Phase 2 `Dispatcher`），MUST NOT 對非就緒單位派工。`persona` MUST 預設為 `'builder'` 且可覆寫。`git_runner` MUST 為可選注入物：給定時 MUST 透傳給 `Dispatcher.dispatch(..., git_runner=...)`（沿用 Phase 2 既有 seam），使測試能以 fake `git_runner` 取代真 git；未給定時不傳（沿用 dispatcher 自身預設，並相容不收 `git_runner` 的 fake dispatcher）。因 `ready_units` 先 `detect_cycles`，`dispatch_ready` 對含循環相依或重複 `slice_id` 的 metas MUST raise `ValueError`（一筆都不派），且對無 `slice_id` 的單位 MUST NOT 以 `task=None` 派工。

#### Scenario: fanout 僅對就緒集經注入 dispatcher 各派一筆

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_dispatches_exactly_ready_set -v`
- **THEN** 測試 MUST 以 **fake dispatcher**（記錄 `dispatch` 呼叫）+ 一組含就緒與非就緒（hold／無 plan／depends_on 未滿足）的 metas 驗證：`dispatch` 被呼叫的次數等於就緒單位數、每次 `task` 對應就緒單位的 `slice_id`、`persona` 為注入值，且非就緒單位 MUST NOT 被派工

#### Scenario: fanout 經真 Dispatcher 配 fake seam（含 fake git_runner）不碰真副作用

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_with_real_dispatcher_fake_seams -v`
- **THEN** 測試 MUST 以真 `Dispatcher` 配 fake `PaneSender`／fake `WorktreeCreator`＋**注入 fake `git_runner`**＋暫存 `JobRegistry` 驗證就緒集被各記成一筆 job，且全程不啟動真 tmux／git／copilot（測試 MUST 以 spy 斷言真 `git` 子行程零呼叫、fake `git_runner` 各單位被呼叫一次）

#### Scenario: fanout 對無 slice_id 單位不以 task=None 派工

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_no_slice_id_not_dispatched -v`
- **THEN** 測試 MUST 驗證 `dispatch=='auto'`、有 `plan` 但 `slice_id` 為 `None` 的 meta 不被派工（`dispatch_ready` 回空清單、fake dispatcher 零呼叫），不得產生 `task=None`／`feature/None` 的 job

#### Scenario: fanout 對重複 slice_id refuse 不重複派工

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_refuses_duplicate_slice_id -v`
- **THEN** 測試 MUST 驗證兩份 metas 共用同一 `slice_id` 時 `dispatch_ready` raise `ValueError`（一筆都不派），不得對同一 `feature/<slice_id>` 重複派工

### Requirement: CLI 提供 ready/fanout 子命令且 main(argv) 可注入

`coordinator-cli` 的 `python -m paulshaclaw.coordinator` 入口 SHALL 新增子命令 `ready --specs-dir <dir>`（輸出就緒單位的 JSON 清單）與 `fanout --specs-dir <dir> [--persona R]`（算就緒集、經 Phase 2 `Dispatcher` 派工、輸出 dispatched jobs 的 JSON）。`main(argv, *, registry=None, pane_sender=None, worktree_creator=None, is_satisfied=None, git_runner=None) -> int` MUST 在 Phase 2 簽名上新增可注入的 `is_satisfied`（未注入時用 `default_is_satisfied`）與可注入的 `git_runner`（`fanout` 透傳給 `dispatch_ready`／`Dispatcher.dispatch`；未注入時沿用 `Dispatcher` 預設真 git——測試一律注入 fake `git_runner` 以保證不啟動真 git），並 MUST 在未注入 seam 時接線真實 seam（不啟動真 tmux／worktree 由測試以注入 fake 保證）。偵測到循環相依時 `ready`／`fanout` MUST 將錯誤輸出至 stderr 並 exit 非零（refuse）。既有 `dispatch`／`jobs`／`stat` 子命令 MUST 維持不變。

#### Scenario: ready 子命令以注入 is_satisfied 列就緒單位

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests.test_main_ready_lists_ready_units -v`
- **THEN** 測試 MUST 以暫存 specs 目錄＋注入 `is_satisfied` 驗證 `main(["ready", "--specs-dir", d], is_satisfied=...)` 回 0 並輸出僅含就緒單位的 JSON

#### Scenario: fanout 子命令以注入 fake 派出就緒集

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests.test_main_fanout_with_fakes -v`
- **THEN** 測試 MUST 以注入的 fake seam＋暫存 registry＋注入 `is_satisfied`＋注入 fake `git_runner` 驗證 `main(["fanout", "--specs-dir", d], ...)` 回 0、就緒集各被記成一筆 job、輸出 dispatched jobs JSON，且全程不碰真 tmux／git／copilot（測試 MUST 以 spy 斷言真 `git` 子行程零呼叫）

#### Scenario: 循環相依時 ready/fanout exit 非零

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests.test_main_refuses_on_cycle -v`
- **THEN** 測試 MUST 以含循環相依的暫存 specs 目錄驗證 `main(["ready", "--specs-dir", d], ...)` 回非零並於 stderr 含循環相依訊息，MUST NOT 派工

### Requirement: 派工指令攜帶 persona 契約（強制點 ①）

coordinator 派工時 SHALL 透過 `build_dispatch_prompt(role, *, task, plan_path, catalog)` 把指定 persona 角色的契約 render 成 **executor-agnostic 純文字 prompt 前言**（不含任何 shell/executor 包裝）。此函式 MUST 為純字串函式、零檔案 I/O（僅嵌入 `plan_path` 參照），且對未知 role MUST raise `ValueError`（fail-closed）。executor argv 的組裝改由 `AgentLauncher`（見 `coordinator-headless-dispatch`）各自負責，本函式只產 prompt 文字。

#### Scenario: 已知角色 render 出契約 prompt 文字

- **WHEN** 以 `role="builder"`、`task` 與 `plan_path` 呼叫 `build_dispatch_prompt`
- **THEN** 回傳的純文字 prompt 包含 persona 契約段（`[PERSONA CONTRACT ... role: builder ...]`）、該 `task`、該 `plan_path` 參照；且**不含** shell/executor 字樣（如 `copilot`、`shlex` 引號包裝）

#### Scenario: 未知角色 fail-closed

- **WHEN** 以不存在於 catalog 的 `role` 呼叫 `build_dispatch_prompt`
- **THEN** raise `ValueError`，不產出任何 prompt

#### Scenario: 純函式零 I/O

- **WHEN** 傳入不存在的 `plan_path`
- **THEN** 仍正常回傳含該路徑參照的 prompt（不讀檔、不 raise）

### Requirement: fan-out 派出真契約指令而非佔位

`coordinator.autonomy.dispatch_ready` SHALL 對每個就緒單位以 `build_dispatch_prompt` 產 prompt、再經注入的 `AgentLauncher` headless 啟動 agent，取代先前的佔位註解字串與 pane 送字模型。

#### Scenario: dispatch_ready 經 AgentLauncher 啟動

- **WHEN** `dispatch_ready` 對一個 `dispatch:auto` 且具 plan 的就緒單位派工
- **THEN** 呼叫注入的 `AgentLauncher.launch`，傳入含 persona 契約段與 plan 路徑的 prompt、該 `slice_id` 與 worktree；且不再產生 `# dispatch <slice_id> (plan=...)` 佔位字串、不經 tmux pane 送字

### Requirement: CLI `complete` 子命令觸發完成側 tick

`coordinator-cli` SHALL 提供 `complete` 子命令，建立 `Dispatcher`（reuse 注入或預設 seam）→ 呼叫 `manager.complete_tick` → 以 JSON 印出 summary、exit `0`，與既有 `ready`/`fanout` 同構。MUST 支援 `--handoff-dir`（預設 `autonomy.DEFAULT_HANDOFF_DIR`）與可選 `--specs-dir`（設定後 `scan_specs` 取 metas，使 summary 附觀測用的 `released`）。`complete` 路徑 MUST NOT 觸發 pane 送字或 worktree 建立（完成側不派工）。

#### Scenario: complete 子命令補寫 manifest 並印 summary

- **WHEN** registry 中有一個已 `done` 但缺 manifest 的 job，執行 `cli.main(["complete", "--handoff-dir", <dir>], registry=<reg>, pane_sender=<fake>, worktree_creator=<fake>)`
- **THEN** 回傳碼 MUST 為 `0`，stdout MUST 為合法 summary JSON 且 `completed` 含該 slice，`<dir>/<slice>.json` MUST 被寫出，注入的 fake sender/creator MUST NOT 被呼叫

### Requirement: CLI `tick` 子命令觸發完整 manager tick

`coordinator-cli` SHALL 提供 `tick` 子命令，建立 `Dispatcher`（reuse 注入或預設 seam）與（依 `--executor`）launcher → 呼叫 `manager.run_tick` → 以 JSON 印出 summary、exit `0`，與既有 `fanout`/`complete` 同構。MUST 支援 `--specs-dir`（必填，`scan_specs` 取 metas）、`--executor`、`--handoff-dir`、`--require-idle`、`--max-load`。

#### Scenario: tick 子命令 idle 未達時印 skipped

- **WHEN** 執行 `cli.main(["tick", "--specs-dir", <dir>, "--require-idle", "--max-load", "0"], registry=<reg>, ...)`（注入 fake seam 使 idle 判定為非 idle）
- **THEN** 回傳碼 MUST 為 `0`，stdout MUST 為合法 summary JSON 且 `skipped` 為 `'not-idle'`

### Requirement: tick/fanout 支援 --allow-unsafe 與 --model

`coordinator-cli` 的 `tick` 與 `fanout` 子命令 SHALL 支援 `--allow-unsafe`（store_true）與 `--model <m>`。`--allow-unsafe` 為真時，建立的 `SubprocessLauncher` MUST 以 `allow_unsafe=True` 構建（放開各 executor 全自動旗標，headless 自主完成不掛）；預設 False。`--model` 設定時 MUST 傳入 `SubprocessLauncher(model=...)`，未設則為 None（各 executor 用預設 model）。注入 launcher（測試）時 MUST 尊重注入物、不覆寫。

#### Scenario: --allow-unsafe 建 allow_unsafe launcher

- **WHEN** 執行 `fanout`/`tick` 帶 `--executor copilot --allow-unsafe`（未注入 launcher）
- **THEN** 建立的 `SubprocessLauncher` MUST `allow_unsafe=True`

#### Scenario: --model 傳入 launcher

- **WHEN** 執行 `fanout`/`tick` 帶 `--executor copilot --model haiku-4.5`（未注入 launcher）
- **THEN** 建立的 `SubprocessLauncher` MUST 帶 `model="haiku-4.5"`

### Requirement: --allow-unsafe fail-closed 綁定就緒集大小

因 `--allow-unsafe` 旁路各 executor 的沙箱/核可，`tick`/`fanout` 在 `--allow-unsafe` 為真時 MUST fail-closed：就緒集（`ready_units`）大於 1 個 slice 時 MUST 拒絕派工並以非零退出（avoid 一次對多個 slice 大量自主越權派工，例如誤指 specs-dir 或真實 specs 含多個 `dispatch:auto`）。`--allow-unsafe` 未設時不施此限。

#### Scenario: unsafe + 多就緒 slice 拒絕

- **WHEN** `--allow-unsafe` 為真且就緒集含 ≥2 個 slice
- **THEN** MUST 以錯誤退出（exit 1），MUST NOT 派工任何 slice

#### Scenario: unsafe + 單一就緒 slice 放行

- **WHEN** `--allow-unsafe` 為真且就緒集恰為 1 個 slice（canary）
- **THEN** MUST 正常派工該 slice

