# Plan：cockpit JOBS 面板接上 cortex（issue #248，A′ 通道）

目標 repo：paulshaclaw｜對應 issue：#248｜PR body 須 `Closes #248`

## 問題

JOBS 面板恆空。舊 `ArtifactAdapter` 讀 pre-cortex 的「目錄下 per-pane `*.json`」檔案契約，start.sh 從沒接線，且 cortex job 無 `pane_id`。真正的 cortex job list 在 manager `status.json`，由 `control.client.read_status()` 取得（cockpit 已 import 此面，manager 面板 `m` 鍵已在用）。

## 決策：A′ = 消費 control.client.read_status()

monitor socket 實測只 serve ProjectState（stage 進度），不含 job。改渲染 `read_status()` 的 slice 派工管線。spec 合規（允許 import 面 = `control.client`），不新增 socket code、不 import `paulsha_cortex.monitor`。

## 範圍（僅動這些檔）

- `paulshaclaw/cockpit/app.py`（JOBS 面板渲染 + tick 重讀）
- `paulshaclaw/cockpit/models.py`（如需 slice-view dataclass）
- `paulshaclaw/cockpit/__main__.py`（移除死掉的 ArtifactAdapter 接線）
- `tests/test_stage11_operator_cockpit.py`（TDD）

## `read_status()` 資料形狀（實測）

`status.json` top keys：`attention`/`held`/`in_flight`/`ready`/`recent_done`/`slices`/`daemon`/`updated_at`。

- `in_flight[]`：`{job_id, slice_id, state}`
- `ready[]`：slice 摘要
- `held[]`：`{slice_id, reasons[]}`
- `attention[]`：`{slice_id, gate_state, job_state, next_actions[], reason, ...}`
- `recent_done[]`：近期完成
- `daemon`：`{idle, last_tick_at, pid}`

## TDD 任務（紅→綠）

### 1. status → job-row 映射（純函式）
- 新增純函式（`app.py` 或 `models.py`）`slices_from_status(status: dict) -> tuple[JobRow, ...]`：把 `in_flight`/`ready`/`held`/`attention`/`recent_done` 攤平成統一 row：`(slice_id, state, source_section)`，狀態字對映既有 `status_style`（running/blocked/attention/done…）。degraded/缺 key 全 fail-soft 回空。
- 測試：餵一份代表性 status.json → 正確 row 數與狀態；缺 key/degraded → 空、不 raise。

### 2. JOBS 面板渲染改源
- `app.py` `_refresh_widgets` 的 JOBS 區塊（現迭代 `jobs_by_pane`）改渲染 `slices_from_status(self.manager_client.read_status())`。
- 標題 `JOBS` 副標顯示 `N slices`（含 daemon idle/pid 提示可選）。
- fail-soft：`read_status()` degraded（daemon 不在）→ 面板顯示 degraded 提示，不空白崩潰。

### 3. tick 內重讀（live）
- `_on_refresh_tick` 增一步刷新 JOBS（重讀 status），使面板隨 manager tick 更新，而非啟動快照。
- 讀取放背景/容錯，不擋 UI（沿用既有 fail-soft 樣式）。

### 4. 退役死掉的 ArtifactAdapter 路徑
- `__main__.py`：移除 `ArtifactAdapter(...).load_jobs_by_pane()` 接線與 `--coordinator-jobs-dir`（或保留 arg 但標 deprecated 且不再驅動 JOBS）。
- `app.py`：`jobs_by_pane` 若仍被 DETAIL/work-list 的 per-pane 狀態引用，改為「cortex job 非 pane-scoped，per-pane 狀態不再由 coordinator 提供」——per-pane 尾綴移除或恆空，不誤導。
- 保留 `JobSummary` 若他處仍用；否則清理。

## 驗收

- [ ] JOBS 面板顯示 `read_status()` 的 slice（in_flight/ready/held/attention/recent_done）
- [ ] 狀態隨 tick 更新（非啟動快照）
- [ ] daemon 不在時 fail-soft degraded，不崩潰、不空白誤導
- [ ] 無 `paulsha_cortex.monitor` import；import 面僅 `control.client`
- [ ] `python -m pytest tests/test_stage11_operator_cockpit.py -q` 綠、全套無回歸

## 邊界

- 不新增 monitor socket consumer（實測不帶 job；spec 的 socket 條款針對 ProjectState live-query，另案）。
- 不改 #249 的 WORK panes 收斂。
