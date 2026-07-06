## ADDED Requirements

### Requirement: dispatch request 型別
control 契約 SHALL 支援 `type=="dispatch"` request（args：`slice_id` 必填、`specs_dir` 選填、`force_hold` 選填布林）；executor 處理順序 SHALL 為 unknown-slice → no-plan → deps-unsatisfied → dispatch-hold → already-active 五道 fail-closed 檢查，全過才經 headless launcher 開 job；done 紀錄成功帶 `job_id/worktree/branch/slice_id`，失敗帶 `error/reason`。

#### Scenario: 正常派發
- **WHEN** dispatch request 指向有 plan、deps 全滿足、`dispatch: auto` 且無活躍 job 的 slice
- **THEN** launcher 啟動 job，done 紀錄含真 job_id 與 worktree

#### Scenario: hold 預設擋下
- **WHEN** 目標 slice `dispatch: hold` 且 request 未帶 `force_hold`
- **THEN** done 紀錄 error `dispatch-hold`，不啟動 job

#### Scenario: force_hold 顯式覆蓋留痕
- **WHEN** 目標 slice `dispatch: hold` 且 request 帶 `force_hold: true`
- **THEN** job 啟動且 done 紀錄含 `{"override": "hold", "requested_by": <caller>}` 稽核欄

#### Scenario: 活躍 job 拒重複派發
- **WHEN** 目標 slice 已有 dispatched/running 中的 job
- **THEN** done 紀錄 error `already-active`，不啟動第二個 job

### Requirement: held backlog 可見性
manager status SHALL 含 `held` 清單（slice_id＋原因：`no-plan`／`dispatch-hold`／`deps-unsatisfied:<dep>`），且 `control.client.read_status()` 與 `/manager status` 輸出 SHALL 傳遞呈現該欄位；舊格式 status（無 held 鍵）SHALL 正規化為空清單。

#### Scenario: held 分類
- **WHEN** specs_dir 內存在有 slice_id 但缺 plan、hold、deps 未滿足三類 spec
- **THEN** status.held 各自帶對應 reason，且與 ready 互斥

#### Scenario: 舊格式相容
- **WHEN** read_status 讀到無 held 鍵的既有 status.json
- **THEN** 回傳 `held: []`，不報錯
