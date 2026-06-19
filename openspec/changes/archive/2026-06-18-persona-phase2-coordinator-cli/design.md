## Context

設計 §7 列出 minimal coordinator CLI 的 reuse 表：送命令進 pane → `daemon._send_to_pane`（`tmux send-keys -t <pane> -l <text>` 再 `Enter`）；建 worktree → `scripts/using-git-worktrees.sh`（其新分支路徑為 `git worktree add -b <branch> <dir> <base>`）；config seam → `core/config.py: CoordinatorSettings`。要補的是 job registry（狀態檔）、CLI 入口（`dispatch`/`jobs`/`stat`）、並行 fan-out（registry 多筆）、完成偵測（branch 新 commit）。

`core/daemon.py` 現有 `LocalCoordinator` 為 counter stub（`create_job(phase, scope, payload) -> {"job_id": f"local-{n}", ...}`），`CoordinatorClient` 是 `Protocol`。本 change **刻意不改** `LocalCoordinator` / `daemon` / `config`（scope 紀律：本階段只新建 `paulshaclaw/coordinator/` package；把 daemon 接到真 coordinator 是後續 wiring 工作）。

整個 package 的設計鐵律：**所有副作用藏在可注入 seam 後，單元測試一律注入 fake**——不啟動真 copilot、真 tmux、真 git worktree。job_id **確定性**（task + 注入計數器，非時間／非亂數），測試可斷言。

## Goals / Non-Goals

**Goals:**
- `JobRegistry`：CRUD + JSON 持久化（預設 `~/.agents/coordinator/jobs.json`，建構子覆寫）、確定性 job_id（`f"{task}-{seq}"`）、corrupt/不可讀狀態檔 fail-closed（raise）。
- `seams.py`：`PaneSender` / `WorktreeCreator` 兩個 `Protocol`；真實作 `TmuxPaneSender` / `ScriptWorktreeCreator` 鏡射既有零件；真實作**不**進單元測試。
- `Dispatcher`：`dispatch(task, persona, pane_id, command)` 建 worktree→送命令→記 job→回 job；`poll_done(job_id, git_runner)` 以 branch 新 commit 標 done；支援並行多 job。
- `cli.main(argv)`：`dispatch`/`jobs`/`stat`，預設接真 seam，可注入 fake 測試。
- 測試全 fake、確定性、不碰真副作用；全套件不回歸。

**Non-Goals:**
- 不改 `core/daemon.py` / `core/config.py`（含不把 `LocalCoordinator` 換成新 registry）。
- 不接 persona contract render／gate（Phase 1 已交付、屬另一條線）、不建 `persona-scope.yml`（Phase 3）、不做 frontmatter `dispatch:auto` triage（Phase 4）。
- 不整包搬 coordinator skill（provider-routing / relay / cron）；只做本流程所需 minimal CLI（設計非目標）。
- 不解 copilot 完成偵測的「最可靠訊號」終局（設計 §13 待 Phase 2 實測）；本 change 先採 **branch 新 commit**（git_runner 可注入），pane-idle / sentinel 留後續。

## Decisions

- **D1 — 確定性 job_id（task + registry-wide 計數器）**：`JobRegistry` 持一個 **registry-wide 單調** `_seq`（建構子 `seq_start=0`，可覆寫；**非 per-task**），`create_job` 先 `_seq += 1` 再組 `job_id = f"{task}-{_seq}"`。**不用** `time`／`uuid`／`random`，故同序呼叫產生同 id，測試可硬斷言。同一 registry 內依序派 task `a`、`b` 得 `a-1`、`b-2`（seq 全域遞增，跨 task 仍唯一）；同一 task 連派得 `mytask-1`、`mytask-2`。`_seq` 隨 registry 實例存活；重載狀態檔時由載入 `seq` 還原起點（見 D2），避免重載後撞 id。
- **D2 — JSON 持久化 + corrupt fail-closed**：狀態檔結構 `{"seq": <int>, "jobs": [<job>, ...]}`。`JobRegistry` 建構時若檔存在 → 讀；JSON 解析失敗 / 非 dict / 缺鍵型別錯 → **raise**（`ValueError`，fail-closed，呼應 `loader.load_catalog` / `handoff.read_manifest`），**MUST NOT** 靜默清空。檔不存在 → 視為空 registry（首次使用，非錯誤）。每次 mutating（create/update）後 `_persist()` 原子寫（先寫暫存再 `replace`），確保並行/中斷不留半檔。`_seq` 以 `max(載入 seq, 0)` 還原，新 job 從該值續編。
- **D3 — seam 為 `typing.Protocol`，真實作鏡射既有零件**：`PaneSender.send(pane_id, text) -> None`、`WorktreeCreator.create(branch) -> str`（回 worktree 路徑）。`TmuxPaneSender.send` 完全鏡射 `daemon._send_to_pane`：`tmux send-keys -t <pane> -l <text>`（literal，避免 shell 解讀）後 `tmux send-keys -t <pane> Enter`，`CalledProcessError`/`FileNotFoundError` → raise `ValueError`。`ScriptWorktreeCreator.create` 鏡射 `using-git-worktrees.sh` 的新分支路徑：`git -C <repo> worktree add -b <branch> <wt_root>/<branch-slug> <base>`，回 target 路徑。真實作只在 `cli.main` 預設接線時實體化；**所有單元測試注入 fake**（記錄呼叫、回固定路徑），故 import 本 package 不需 tmux/git。
- **D4 — Dispatcher 順序與並行**：`dispatch(task, persona, pane_id, command)`：(1) `worktree = worktree_creator.create(branch)`（branch 由 task 推導 `f"feature/{task}"`，或呼叫者傳入；本 change 採 task 推導以收斂介面）；(2) `pane_sender.send(pane_id, command)`（送的是呼叫者給的完整 command 字串，例 `copilot --model gpt-5.4 --yolo -p "<契約+PROMPT>"`——本 change 不組裝 copilot 指令，只忠實轉送）；(3) `registry.create_job(task, persona, branch, pane_id, worktree)`，status=`dispatched`；(4) 回 job dict。先建 worktree 再送命令：若 worktree 失敗（raise）則不送命令、不記 job（fail-closed，避免記到沒 worktree 的 job）。並行：多次 `dispatch` 各自一筆 job，pane+worktree 天然隔離，registry list 互不污染。
- **D5 — 完成偵測：branch 新 commit（git_runner 可注入）**：`poll_done(job_id, git_runner)`：取 job 的 branch，`git_runner` 為 callable（`(args: list[str]) -> str`，預設真實作呼 `git rev-parse <branch>`），比對 commit 是否異於派工當下記錄的 baseline（job 記 `dispatch_head`：dispatch 時若有 git_runner 可記，否則 None）。簡化版：`poll_done` 收到的 git_runner 回傳的 head 與 job 的 `dispatch_head` 不同 → `update_status(job_id, "done")` 並回更新後 job；相同 → 維持原 status。測試注入 fake git_runner 回固定 head，斷言狀態轉移。設計 §13 指明完成偵測待實測，故 git_runner 設計成可換（pane-idle / sentinel 日後替換同介面）。
- **D6 — CLI 邏輯/殼分離、可注入**：`cli.main(argv=None, *, registry=None, pane_sender=None, worktree_creator=None) -> int`。argparse 子命令 `dispatch`（`--task/--persona/--pane/--command`）、`jobs`、`stat <job_id>`。三 seam 預設 `None` → `main` 內實體化真實作（`TmuxPaneSender` / `ScriptWorktreeCreator` / `JobRegistry()`）；測試一律全注入 fake。`dispatch` 印新 job JSON、`jobs` 印 list JSON、`stat` 印單 job JSON（查無 → stderr + exit 1）。成功 exit 0。`__main__.py` 僅 `sys.exit(cli.main())`。
- **D7 — 不依賴 core/config 載入**：本階段 worktree root / base ref 以 `ScriptWorktreeCreator` 建構子參數帶（預設 `WT_ROOT=/home/paul_chen/prj_pri/paulshaclaw-worktrees`、`base=main`、`repo=<repo root>`），**不**讀 `CoordinatorSettings`（避免觸碰 config 載入路徑、維持 package 自我封裝）。日後 wiring 階段再由 daemon 用 `CoordinatorSettings` 餵入。

## Risks / Trade-offs

- [job_id 撞號（重載狀態檔後）] → D2 以載入的 `seq` 還原計數器、新 job 續編，避免重載後 `task-1` 撞既有；同 task 重派也由單調 seq 區分。Trade-off：job_id 不含時間，無法由 id 看派工時序——可接受（job 內有 `created_at`，且確定性是測試硬需求，設計明令禁時間/亂數 id）。
- [corrupt 狀態檔 fail-closed 可能擋住正常使用] → 正是意圖（壞狀態不可靜默吞，呼應 loader/handoff 慣例）；操作者刪檔即重建空 registry（檔不存在非錯誤）。
- [完成偵測用 branch 新 commit 不完全可靠（copilot 未 commit 即視為未完成）] → 設計 §13 已標此為待實測風險；本 change 把偵測器設計成 git_runner 可注入的 seam，pane-idle / sentinel 日後可換入同介面，不需改 dispatcher 結構。
- [真實作 `ScriptWorktreeCreator` 直呼 `git worktree add -b` 而非整段跑 `using-git-worktrees.sh`] → 該 script 為 TSV 批次驅動（讀 map 一次建多個），對「單 branch 即時建」不 ergonomic；故鏡射其**新分支那行語意**而非整段呼叫。風險低（語意一致）、且真實作不進測試。
- [TmuxPaneSender 送 literal 字串] → 完全鏡射 `daemon._send_to_pane`（`-l` literal + 獨立 `Enter`），避免 shell 對 command 內引號/`$` 的二次解讀；與既有 daemon 行為一致。
