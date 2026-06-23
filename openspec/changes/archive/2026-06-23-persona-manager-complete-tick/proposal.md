## Why

Phase B（#112）已做派工側：`dispatch_ready` 算就緒集並經 headless `AgentLauncher` 啟動 agent。但 umbrella §4.3 的**完成側**（`poll_headless_done → 跑 gate → 寫 runtime/handoff/<slice>.json → 釋放下游 depends_on`）**不在任何 loop 裡跑**——派出去的 job 跑完後沒人寫 handoff manifest，下一趟 `dispatch_ready` 的 `default_is_satisfied` 永遠看不到 `gate_status=='passed'`，fan-out 的相依推進就此卡死。這是 Phase C（systemd timer）真正有用的前置基石（#121）。

## What Changes

- 新增 `paulshaclaw/coordinator/manager.py`：純編排函式 `complete_tick(dispatcher, *, gate_runner=None, handoff_dir=DEFAULT_HANDOFF_DIR, metas=None, clock=_utcnow)`，輪詢 in-flight job → `poll_headless_done` 偵測完成 → 寫 completion manifest → 使下一趟 `dispatch_ready` 能釋放下游。
- 釋放判定來源（#104 留開放）採 **exit-code 主導 + shadow gate**：`gate_status='passed' if completion=='done' else 'failed'`；persona diff gate 以 shadow 跑、結果存入 manifest `gate_verdict` 觀測欄位，**永不改 `gate_status`**、不擋釋放。
- completion manifest 落 `runtime/handoff/<slice>.json`（= `default_is_satisfied` 讀的同一路徑），含 `slice_id/gate_status/completion/exit_code/branch/gate_verdict/completed_at`。
- reconciliation：終態但缺 manifest 者本趟補寫；tick 冪等；per-job 例外隔離（比照 `dispatch_ready`）。
- `coordinator` CLI 新增 `complete` 子命令作為手動／Phase C timer 的入口。

## Capabilities

### New Capabilities

- `coordinator-completion-tick`: coordinator 完成側 tick——輪詢 in-flight headless job、由 `poll_headless_done` 偵測完成、以 exit-code 主導寫 `runtime/handoff/<slice>.json`（shadow gate 僅觀測）、reconciliation 補寫、冪等與 per-job 隔離，使下一趟 `dispatch_ready` 經 `default_is_satisfied` 釋放下游 `depends_on`。

### Modified Capabilities

- `coordinator-cli`: 新增 `complete` 子命令（建 Dispatcher → 跑 `complete_tick` → 印 summary JSON），與既有 `ready`/`fanout` 同構；`--handoff-dir`、可選 `--specs-dir`（觀測 `released`）。

## Impact

- 代碼：新增 `paulshaclaw/coordinator/manager.py`、`tests/test_coordinator_manager.py`、`tests/test_coordinator_cli_complete.py`；修改 `paulshaclaw/coordinator/cli.py`。
- 設計依據：`docs/superpowers/specs/2026-06-23-persona-manager-complete-tick-design.md`；計畫 `docs/superpowers/plans/2026-06-23-persona-manager-complete-tick.md`。
- reuse 既有積木（`dispatcher.poll_headless_done`、`JobRegistry`、`persona.handoff.write_manifest`、`persona.gate.build_verdict`、`autonomy.default_is_satisfied`），零重造邏輯。
- 不動派工側（`dispatch_ready`/`AgentLauncher`）與互動路徑（`route_to_agent`）。
- 仍 shadow（gate 不強擋）。
- 明確留 Phase C(#122)：合併 fanout+complete 單一 tick、systemd timer、`--require-idle`、builder→reviewer handoff-message schema gate、failed job retry/requeue。
