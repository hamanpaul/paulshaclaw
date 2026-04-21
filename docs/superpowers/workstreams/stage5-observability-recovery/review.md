# stage5-observability-recovery / review

## Review 範圍

- `paulshaclaw/observability/__init__.py`
- `paulshaclaw/observability/baseline.py`
- `tests/test_stage5_observability_recovery.py`
- `docs/ops/recovery.md`
- `openspec/specs/stage5/spec.md`
- `docs/superpowers/workstreams/stage5-observability-recovery/evidence/`

## 自我 code review 結果

1. health report、error record、raw log policy、chaos matrix 都已封裝為純資料結構與純函式，便於後續接到 Stage1/2 runtime 而不引入額外副作用。
2. 測試先以 `ModuleNotFoundError` 留下 red evidence，再補實作轉綠，符合本輪嚴格 TDD 要求。
3. 文件已對齊實作中的欄位名稱與 threshold 數值，避免 spec / playbook / code 三邊漂移。
4. 本輪維持最小 diff，未回寫 Stage1/2/3/4 既有檔案。

## 風險

- 目前 health probes 與 thresholds 是 baseline 草案，尚未接上實際 systemd、tmux socket、queue exporter，因此數值仍需實機校正。
- raw log policy 只處理裁切，不包含真正的 secret redaction engine；上游若直接餵入敏感資料，仍需靠後續 Stage6 治理補強。
- full restart playbook 假設服務名稱固定為 `paulshaclaw-daemon.service`、`paulshaclaw-bot.service`、`paulshaclaw-janitor.service`；若部署命名不同，文件要同步調整。

## 後續

1. 將 `build_health_report()` 接到 Stage1 `/status` 與 tmux/session 檢查。
2. 將 `build_error_record()` 寫入實際 log sink，並在 Stage6 做 schema 驗證。
3. 把 chaos matrix 轉成可執行 smoke / recovery 腳本，取代目前的靜態 baseline。

## 結論

- 結論：可合併。
- 理由：TDD red / green / final 證據完整，文件與 spec 已可供後續 stage consume，且無阻斷性問題。
