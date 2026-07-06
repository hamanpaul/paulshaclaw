## Why

`complete_tick` 以「manifest 檔存在即 skip」為冪等判準（slice_id 為唯一 key）——同 slice retry/requeue 的新 run 結果永遠寫不進去，第一輪 failed 卡死下游依賴（#132）。

## What Changes

- manifest 內容加 `job_id`（additive；檔名/位置不動，消費端 `default_is_satisfied` 零改）。
- 冪等規則改三態：同 job_id → skip（真冪等）；不同 job_id → overwrite（新 run 勝，gate_status/verdict/completed_at 重算）；壞檔/缺 job_id（舊格式）→ overwrite（fail-safe，一次性自然升級）。
- 「一 slice 一活躍 job」不變量顯式化（run_tick 既有過濾＋G1 already-active guard 兩道防線）；異常雙 terminal 案例釘住行為＋warning。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `coordinator-completion-tick`: manifest 冪等語意由「存在即 skip」改為 job_id 比對三態；requeue 後新結果可落地。

## Impact

- 受影響碼：`paulshaclaw/coordinator/manager.py`（complete_tick）、handoff 寫入 helper。
- 相容：manifest additive 欄位；`default_is_satisfied`/`recent_done_provider` 零改。
- 依據：`docs/superpowers/specs/2026-07-06-g4-complete-tick-idempotency-design.md`（含 codex 審查修正：不變量顯式化）。
