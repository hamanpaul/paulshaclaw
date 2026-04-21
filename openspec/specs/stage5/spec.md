# stage5 Specification

## Purpose

Stage5 SHALL 定義 observability / recovery 基線，讓 Stage1 runtime 與 Stage2 memory pipeline 能被一致地觀測、記錄錯誤、保留最小必要 raw log，並提供可重複執行的 tmux crash / full restart 復原流程。

## Requirements

### Requirement: Health probes 與健康報表基線

Stage5 MUST 提供可聚合的 health probe 結構，至少覆蓋 `daemon`、`memory_pipeline`、`tmux_server`。健康報表輸出 MUST 包含 `ok`、`status`、`generated_at`、`daemon_snapshot`、`summary`、`failed_components`、`probes`。只要任一 probe 為 `fail`，整體 `status` MUST 為 `fail`，且 `ok` MUST 為 `false`。

#### Scenario: 健康報表可聚合 pass / warn / fail

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage5_observability_recovery.HealthProbeTests -v`
- **THEN** 測試 MUST 驗證 summary 計數正確，且 `tmux_server=fail` 會讓整體健康報表進入 `fail`

### Requirement: 錯誤記錄格式固定為 stage5.error.v1

Stage5 MUST 提供統一的錯誤記錄格式，至少包含 `timestamp`、`schema_version`、`level`、`component`、`event`、`message`、`error_type`、`recoverable`、`action`、`context`。`schema_version` MUST 固定為 `stage5.error.v1`，且輸出 MUST 可直接序列化為 JSON。

#### Scenario: 錯誤記錄可直接進 audit / evidence

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage5_observability_recovery.ErrorRecordTests -v`
- **THEN** 測試 MUST 驗證欄位集合固定、可 JSON 序列化，且 `recoverable=false` 仍保留 `action`

### Requirement: Metrics 預設閾值草案

Stage5 MUST 提供至少五個核心 metrics 的預設閾值草案：`heartbeat_age_seconds`、`queue_backlog`、`restart_count_10m`、`error_burst_5m`、`log_disk_usage_percent`。每個 metric MUST 定義 `warn`、`critical`、`unit`、`rationale`。

#### Scenario: 預設閾值覆蓋核心訊號

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage5_observability_recovery.ThresholdTests -v`
- **THEN** 測試 MUST 驗證五個 metrics 的 warn / critical 值與草案一致

### Requirement: Raw log 保留與裁切規則

Stage5 MUST 定義 raw log retention policy，至少包含 `retention_days`、`max_bytes`、`head_bytes`、`tail_bytes`。當 payload 超過 `max_bytes` 時，系統 MUST 保留頭尾樣本並插入 `...[truncated N bytes]...` 標記；輸出 MUST 回報 `truncated`、`original_bytes`、`stored_bytes`。

#### Scenario: 過大 raw log 會被裁切且保留頭尾

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage5_observability_recovery.RawLogPolicyTests -v`
- **THEN** 測試 MUST 驗證過大 payload 被裁切、保留 head/tail 內容，且 `stored_bytes` 不超過 policy 限額

### Requirement: tmux crash 與 full restart playbook

Stage5 MUST 在 `docs/ops/recovery.md` 定義至少兩條可操作復原路徑：`tmux server crash` 與 `full runtime restart`。文件 MUST 描述觸發條件、復原步驟、驗證命令與 evidence 位置。

#### Scenario: Recovery 文件含 tmux crash / full restart 步驟

- **WHEN** 審查者檢視 `docs/ops/recovery.md`
- **THEN** 文件 MUST 同時包含 `Playbook: tmux server crash` 與 `Playbook: full runtime restart` 章節，且每章節都列出驗證命令

### Requirement: Chaos / recovery 測試矩陣與證據歸檔

Stage5 MUST 提供 chaos / recovery baseline matrix，至少涵蓋 `tmux-server-crash` 與 `full-runtime-restart` 兩種情境，並為每個情境列出 `fault`、`expected_status`、`checks`、`evidence_files`。測試 red / green / final 證據 MUST 歸檔至 `docs/superpowers/workstreams/stage5-observability-recovery/evidence/`。

#### Scenario: Chaos matrix 覆蓋 tmux 與 full restart

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage5_observability_recovery.ChaosMatrixTests -v`
- **THEN** 測試 MUST 驗證 `tmux-server-crash` 與 `full-runtime-restart` 都存在，且 evidence file 路徑帶有 run id 前綴

#### Scenario: Stage5 測試 evidence 完整保留 red / green / final

- **WHEN** 審查者列出 `docs/superpowers/workstreams/stage5-observability-recovery/evidence/`
- **THEN** 目錄 MUST 至少包含一份 `red`、一份 `green`、一份 `final` 測試輸出，以及一份 chaos matrix artifact
