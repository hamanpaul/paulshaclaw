# cockpit ↔ cortex 修正設計（#248 JOBS + #249 WORK panes）

日期：2026-07-21｜狀態：approved（brainstorm 定案）

## 背景

Stage 11 operator cockpit 兩個可用性缺陷：

- **#248**：JOBS 面板恆空。舊 `ArtifactAdapter` 讀「目錄下 per-pane `*.json`」的 pre-cortex 檔案契約，start.sh 從沒傳 `--coordinator-jobs-dir`，且 cortex job 無 `pane_id`——四環全斷。
- **#249**：WORK panes 清單撈全 tmux server（13 session/~40 pane）、summary 全撞 hostname `9900X`、看不出 cockpit 自身 pane。

## 執行模型：paulshaclaw-scoped cortex dogfood

以 cortex 現行 runtime（`deck compile` → `coordinator tick` → Dispatcher fanout → 完成偵測 → handoff）把兩修正當真實任務派工，證明 cortex 能派工到任意 repo（paulshaclaw），而非只自我修。executor=copilot(gpt-5.4)。隔離沙箱（獨立 `PSC_COORDINATOR_ROOT`/`PSC_CONTROL_ROOT`/`PSC_SPECS_ROOT`）不碰 live daemon。校對 cortex workflow，遇缺陷開 issue 到 paulsha-cortex repo。

## #248 修法（A′：消費 control.client）

**決策**：monitor socket 實測只 serve ProjectState（專案 stage 進度），不含 job list。改由 **`control.client.read_status()`**（cockpit 已 import 的允許面）渲染 manager 的 slice 派工管線。

- JOBS 面板改渲染 `read_status()` 的 `in_flight`/`ready`/`held`/`attention`/`recent_done` slice。
- 每個 refresh tick 重讀（live，非啟動快照）。
- 退役死掉的 `ArtifactAdapter`/`jobs_by_pane` 檔案路徑（per-pane job 映射對 cortex 不適用——cortex job 非 pane-scoped）。
- spec 合規：不新增 socket code、不 import `paulsha_cortex.monitor`。

## #249 修法（範圍 + summary + 自我定位）

- **範圍**：`store.py` `candidate_section` 預設收斂到 cockpit 自身 session（跨 session 不再淹沒）；排序讓自身 window 的 pane 在前。
- **summary**：`tmux.py` `derive_summary` 在 title 為空**或 title == hostname**（`host_short`）時 fallback 到 cwd basename（`pane_current_path`）→ 再退 `[command]`。需在 `LIST_PANES_FORMAT` 增 `#{pane_current_path}`、`#{host_short}`，`PaneRecord` 增對應欄。
- **自我定位**：WORK 面板副標顯示 cockpit 自身 `session:window`（you-are-here）。

## 驗收

- #248：JOBS 面板顯示 cortex 現有 slice，狀態隨 tick 更新；無 `paulsha_cortex.monitor` import。
- #249：預設只列自身 session 的 pane；同 window 多個 idle bash pane summary 可區分；一眼看出 cockpit 所在。
- 兩者單測綠、全套 pytest 無回歸。
