---
work_item: jobs-execution-identity
status: accepted
---

# cockpit 實際 executor/model consumer

## Requirements

對應 hamanpaul/paulshaclaw#328。

本工作源自 2026-09-07 使用者核可的五件 issue 修正計畫與 Cortex 平行派工指令。accepted 僅表示規格可執行，不表示程式或驗收已完成。

使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。只處理本件 issue；所有實作、測試、OpenSpec、文件及 changelog 限本件 scope。不同工作線的 pyproject／CI／README 等共用檔須在各自 branch 修改，交由整合者處理衝突，不跨 worker worktree 寫入。

採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為 FAIL，接受風險需明文、有界且可追溯。禁止跳 gate 或手改 Cortex registry。部署、發布與本機 skill target 切換由 operator 整合驗收後執行，不由本 worker 自行進行；不得對外送 Telegram、覆寫既有 release、變更共享 service/config。PR 可依 Cortex 既有授權 gate 交付；不得僅憑 worker exit 0 宣告完成。

工作 E：#328 executor／model 可觀測性

建議 branches：Cortex `feature/jobs-execution-identity`，paulshaclaw `feature/328-jobs-execution-identity`。

責任鏈：Cortex registry job／WorkflowStep → Cortex status projection → paulshaclaw `_ingest_workflow_run()` → `JobRow` → JOBS widget。Cortex 決定身份事實，cockpit 只解析與顯示。

- [ ] 先核對 Cortex remote、pin、`WorkflowStep` 與 job binding；重用既有 status identity 契約（若已有修復）。同 phase 有多卡與 retries，不能只取第一個 phase 相同的 step。
- [ ] producer 選取順序：已綁定的當前 in-flight job → 當前卡最後一次實際執行的 job → 沒有可證明 job 時顯示未派工／unknown。必須校驗 repo、run、card、attempt 綁定，不能跨 run 借用舊模型。planned step 身份若顯示，明確標為「預定」，不得冒充實際執行。
- [ ] 提案為 additive status 欄位：`executor`、`model`、`job_id`、`card`、`identity_source` 與執行狀態；內部 job `model_id` 映射成公開 `model`。欄位名稱以既有上游契約核對後固定，producer／consumer 使用同一組 fixture。
- [ ] 所有可顯示 workflow 的 status sections 都須覆蓋，不只 attention。claim／not_claimable 無 worker 時顯示未派工；manager deterministic step 明示 deterministic；needs_human 的最後執行者標示「上次執行」，避免被讀成仍在跑。
- [ ] consumer 在 JobRow 增加有預設值的欄位，ingest 使用 typed fallback；缺欄位的舊 Cortex 保持可讀，顯示未提供，不從 persona 推 executor/model。
- [ ] JOBS 加 agent · model 的 detail/trailer；保留 project/stage/persona、reason、next_actions、run_id；窄寬度可摘要，但展開後完整模型字串可見，處理 CJK 寬度與 markup 字元。
- [ ] 測試矩陣：新／舊 schema、缺值／null／型別錯誤、同 phase 多卡、provider retry／換模型、verify→review、未派工、阻塞、完成、跨 repo 同 work_id、未知 executor、長 model、窄面板與刷新。
- [ ] 上游 PR merge 後固定實際 SHA；下游更新 Cortex pin，跑 `tests/test_cortex_alignment.py`。既有約定要求 Hippo／Cortex lifecycle 對齊，必要時成對移 pin，但只採經驗證的版本；不能直接用 floating main。
- [ ] 在隔離測試環境用已安裝的 Cortex producer 輸出，餵給已安裝的 paulshaclaw cockpit，與 registry 的實際 job 對照。Textual headless 測試覆蓋 render／刷新；保留去識別化 snapshot 與結果。

驗收：operator 看得到某 run 的當前或上次實際 executor／model，以及清楚的狀態；來源可追到具相同 run/card 綁定的 job。完成 producer、consumer、pin 與 runtime 整合證據後，才由下游 PR `Closes #328`。
