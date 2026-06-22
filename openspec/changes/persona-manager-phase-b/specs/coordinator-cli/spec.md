## MODIFIED Requirements

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

### Requirement: fan-out 經 headless launcher 派工而非佔位

`coordinator.autonomy.dispatch_ready` SHALL 對每個就緒單位以 `build_dispatch_prompt` 產 prompt、再經注入的 `AgentLauncher` headless 啟動 agent，取代先前的佔位註解字串與 pane 送字模型。

#### Scenario: dispatch_ready 經 AgentLauncher 啟動

- **WHEN** `dispatch_ready` 對一個 `dispatch:auto` 且具 plan 的就緒單位派工
- **THEN** 呼叫注入的 `AgentLauncher.launch`，傳入含 persona 契約段與 plan 路徑的 prompt、該 `slice_id` 與 worktree；且不再產生 `# dispatch <slice_id> (plan=...)` 佔位字串、不經 tmux pane 送字
