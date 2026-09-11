# Open issues Cortex 派工紀錄

2026-09-07 Asia/Taipei。使用者授權：派入 Cortex 開始平行作業。由 Cortex Manager 單一 writer 建立／推進 workflow，未直接修改 jobs.json 或驗收 evidence。

## 已啟動

| Issue | Work item | Workflow run | 最近派出 job |
|---|---|---|---|
| #324 | deploy-testpilot-case | workflow-d60712811d3822ea1651 | wf-d3c2b7be35-tdd-red-6 |
| #296 | bro-canonical-source | workflow-26b097725967cf882cb5 | wf-e3a0c5f0a9-tdd-red-7 |
| #326 | deploy-template-packaging | workflow-8da1ac520ef0bc03aba8 | wf-a9aac306b6-worktree-isolation-8 |

#324 builder 沿用原 AGY 指定，run override 為 agy/gemini-3.8-flash-high；#296、#326 採共享模型 policy，Claude session limit 後由 Cortex 自動改用 codex/gpt-5.6-luna。隔離 worktree 根在 paulshaclaw-worktrees；accepted plan 已以 hash 綁入各 run。

#326 第一個 Codex 回報將 run ID 少寫一個字元，Manager 以 run/card mismatch 拒收；使用 exact run/card 的正式 retry-card 重派為 job 8，未竄改回報。#324、#296 已通過 worktree-isolation，RED 尚未驗收。

## 進件但未啟動

- #325 → install-prerequisites：Todo、accepted spec/design/plan 及 issue link 已建立；未送 start、未加 auto label。等待 #324 merge 且精確歷史 RED report 可查，再由 operator start。
- #328 → jobs-execution-identity：只擁有 paulshaclaw consumer/pin；同樣不 start、不加 auto label。等待上游 producer merge，核對正式欄位 fixture 與 SHA，再 start。
- 上游 producer 已建立 hamanpaul/paulsha-cortex#828 與 workflow-execution-identity-producer 的 Todo/spec/design/plan、Manager issue link。Monitor 尚未把新 issue 納入 confirmed source，因此沒有 WorkflowRun；auto request 被 fail-closed 拒絕，不能稱為已排程自動啟動。已透過 EventSpool.emit_github_object 發送只含 repo/kind/number 的 refresh hint，仍需 Monitor 向 GitHub 驗證。

## 後續正式入口

使用與 daemon 同源的 runtime 入口（cwd 為 paulsha-cortex-runtime-main，python3 -m paulsha_cortex.cli）。PATH 的 pipx Cortex 0.1.8 不接受新診斷欄位 next_step_hint，無法用其 stat 載入 registry；本次未升級或重啟共享 service。

1. work show workflow-execution-identity-producer --repo hamanpaul/paulsha-cortex --json，確認 source 含 github_issue:hamanpaul/paulsha-cortex#828。
2. run work start workflow-execution-identity-producer --repo hamanpaul/paulsha-cortex --combo feature-oneshot --json。
3. 核對 start request 成功後，以 run work resume 推進並查實際 job；不得略過 source authority。
4. #324 merge/RED → #325 start；#828 merge/fixture/SHA → #328 start。這兩個依賴目前為 operator-managed hold，不宣稱 Cortex 有已配置的跨 work-item DAG 自動解鎖。

## 邊界

保留兩 repo 原有未提交內容，沒有 stage/commit 其他工作。Cortex checkout 為新增 intake 文件開 feature/open-issues-dispatch-20260907 分支；實作 workers 使用 Manager 隔離 worktree。沒有發布 release、切換 bro runtime 或送 Telegram。

此檔是時間點紀錄；最新狀態以 Cortex status/request、job logs 與 registry 唯讀投影為準。Logs 根：~/.agents/coordinator-cortex/logs/workflow/。
