# Stage5 Recovery Playbook

## 範圍

本文件定義 Stage5 observability / recovery 基線，覆蓋：

- health probes 與錯誤記錄格式
- metrics 預設閾值草案
- raw log 保留與裁切規則
- tmux crash / full restart 手動復原流程
- chaos / recovery 驗證與 evidence 產出位置

## Health probes

| probe | 來源 | warn 條件 | fail 條件 | 備註 |
|---|---|---|---|---|
| `daemon` | Stage1 `/status` | heartbeat age > 30s | heartbeat age > 90s | Stage5 只 consume Stage1 snapshot |
| `memory_pipeline` | Stage2 queue / janitor backlog | backlog > 10 | backlog > 25 | backlog 持續升高要保留 raw log 尾端樣本 |
| `tmux_server` | `tmux ls` / socket 檢查 | session 缺少必要 pane | 無法列出 session 或 socket 消失 | 失敗時直接進 tmux crash playbook |
| `log_sink` | log volume 使用率 | disk usage > 70% | disk usage > 85% | fail 時先裁切 raw log，再做輪替 |

## 錯誤記錄格式

錯誤事件統一使用 `stage5.error.v1` JSON shape：

```json
{
  "timestamp": "2026-04-21T00:00:00Z",
  "schema_version": "stage5.error.v1",
  "level": "error",
  "component": "tmux-supervisor",
  "event": "restart-failed",
  "message": "tmux restart exceeded budget",
  "error_type": "RuntimeError",
  "recoverable": false,
  "action": "page-operator",
  "context": {
    "attempt": 4,
    "session": "ops"
  }
}
```

欄位規則：

- `level` 先固定為 `error`，warning/info 留待後續版本擴充。
- `recoverable=false` 時必須搭配明確 `action`，避免只記錄不處置。
- `context` 只放可序列化資料，不放 token、cookie、原始密鑰。

## Metrics 預設閾值草案

| metric | warn | critical | 單位 | 用途 |
|---|---|---|---|---|
| `heartbeat_age_seconds` | 30 | 90 | seconds | 判定 daemon 是否卡死 |
| `queue_backlog` | 10 | 25 | items | 判定 Stage2 pipeline 是否塞住 |
| `restart_count_10m` | 2 | 4 | restarts/10m | 避免 crash loop |
| `error_burst_5m` | 5 | 10 | errors/5m | 觸發人工介入 |
| `log_disk_usage_percent` | 70 | 85 | percent | 啟動裁切與輪替 |

## Raw log 保留與裁切規則

- 保留天數：預設 7 天。
- 單筆 raw log 上限：預設 `32768 bytes`。
- 裁切方式：保留 head `8192 bytes` + tail `8192 bytes`，中間以 `...[truncated N bytes]...` 佔位。
- 觸發時機：
  - 單筆 payload 超過上限。
  - backlog / error burst 進入 warn 以上，需要保留尾端錯誤樣本而不是整份 dump。
  - log disk usage 進入 warn 以上。
- 不可保留內容：
  - token / cookie / password / private URL / email 等敏感字串。
  - 若 redactor 尚未落地，至少先避免把這些欄位寫入 `context`。

## Playbook: tmux server crash

### 觸發條件

- `tmux ls` 失敗。
- `tmux_server` probe 進入 `fail`。
- Stage1 `/status` 仍可回應，但 pane 無法列出。

### 復原步驟

1. 先記錄現況：
   - `tmux ls`
   - `python3 -m paulshaclaw.core.daemon --config <config> --command /status`
2. 確認沒有其他 agent 正在重建 tmux session；若有人在處理，避免重複操作。
3. 重啟 tmux server：
   - `tmux kill-server`（僅在 server 半死不活且確認無活躍 session 時使用）
   - 重新建立 canonical session / panes
4. 重新載入 Stage1 daemon 所需 pane mapping。
5. 驗證：
   - `tmux ls`
   - 確認必要 pane 標題與 task id 已重建
   - 再跑一次 `/status`
6. 將 before / after 輸出寫入 Stage5 evidence。

## Playbook: Telegram runtime restart

### 觸發條件

- `paulshaclaw.service`、`paulshaclaw-telegram.service` 或 janitor placeholder 任一持續 crash loop。
- `restart_count_10m` 進入 critical。
- `error_burst_5m` 持續升高且單點重啟無效。

### 復原步驟

1. 先收集三個服務狀態：
   - `systemctl --user status paulshaclaw.service`
   - `systemctl --user status paulshaclaw-telegram.service`
   - `systemctl --user status paulshaclaw-janitor.service`
2. 先確認 Telegram listener 的環境與設定：
   - `PSC_TELEGRAM_BOT_TOKEN` 已在 `~/.config/paulshaclaw/paulshaclaw.telegram.secret.env` 提供
   - 若有設定，`PSC_TELEGRAM_EXPECTED_USERNAME` / `PSC_TELEGRAM_EXPECTED_BOT_ID` 與實際 bot 身分一致
   - Stage 1 設定由 `--config <path>` 或 `PSC_STAGE1_CONFIG` 提供，且設定檔可讀
3. 若是 local `scripts/start.sh` 場景，先確認 `~/.agents/log/telegram.log` 正常寫入。
4. 若是 deployed systemd 場景，使用 journald 觀察：
   - `journalctl --user -u paulshaclaw-telegram.service -f`
   - `journalctl --user -u paulshaclaw.service -f`
5. 依序停止 Telegram listener、janitor、daemon，避免重啟期間重複 ingest。
6. 清理過時 pid/socket，保留 raw log 尾端證據。
7. 依序啟動 daemon -> Telegram listener -> janitor：
   - `systemctl --user restart paulshaclaw.service`
   - `systemctl --user restart paulshaclaw-telegram.service`
   - `systemctl --user restart paulshaclaw-janitor.service`
8. 驗證：
   - `/status` 成功
   - `tmux ls` 成功
   - local `scripts/start.sh` 路徑下，`~/.agents/log/telegram.log` 持續寫入且沒有 token 相關錯誤
   - deployed systemd 路徑下，`journalctl --user -u paulshaclaw-telegram.service` 中沒有 token/config 錯誤
   - `PSC_TELEGRAM_BOT_TOKEN` 存在且非空
   - `PSC_STAGE1_CONFIG` 指向可讀設定檔，或 `--config` 明確提供設定檔
   - 若有設定 `PSC_TELEGRAM_EXPECTED_USERNAME` / `PSC_TELEGRAM_EXPECTED_BOT_ID`，啟動時會先做 bot 身分比對
   - `/dispatch sample-task` 若尚未接上真實 coordinator，會 fail closed 並回傳 `coordinator backend 未設定`
    - queue backlog 回落或至少不再增加
9. 若仍失敗，升級為人工介入並附上 `stage5.error.v1` 紀錄。

## Playbook: memory pipeline 阻塞

1. 檢查 `queue_backlog`、`error_burst_5m` 是否超過閾值。
2. 對 raw log 套用裁切規則，保留 head / tail 樣本。
3. 先讓 janitor / replay 停止擴大 backlog，再處理上游。
4. 確認 Stage2 路徑仍維持 `inbox -> work-centric -> knowledge`，不得直接寫 `knowledge/*` 規避 backlog。
5. 恢復後將 backlog 前後數值與 log 樣本寫入 evidence。

## Evidence 位置

- `docs/superpowers/workstreams/stage5-observability-recovery/evidence/20260421T120000+0800-stage5-unittest-red.log`
- `docs/superpowers/workstreams/stage5-observability-recovery/evidence/20260421T121500+0800-stage5-unittest-green.log`
- `docs/superpowers/workstreams/stage5-observability-recovery/evidence/20260421T122500+0800-stage5-chaos-matrix.json`
- `docs/superpowers/workstreams/stage5-observability-recovery/evidence/20260421T123500+0800-stage5-unittest-final.log`
