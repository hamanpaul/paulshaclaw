## Why

真 coordinator（2.1k LOC）建好未通電：bot `/dispatch` 綁 UnavailableCoordinator、daemon 用 LocalCoordinator 假 job id（epic #14 開自 2026-04-29）；manager status 對「有 spec/plan 但未就緒」全隱形。站穩閘 G1＝把 dispatch 接上既有 control 契約並補 backlog 可見性。

## What Changes

- `control/contract.py` `REQUEST_TYPES` 加 `"dispatch"`（args：slice_id／specs_dir?／force_hold?），done 紀錄帶 job_id/worktree/branch 或 error reason（additive）。
- manager_daemon executor 處理 dispatch：unknown-slice／no-plan／deps-unsatisfied／**dispatch-hold（預設擋，`force_hold` 顯式覆蓋＋稽核欄）**／**already-active（一 slice 一活躍 job guard）** 五拒絕路徑，通過走既有 headless launcher。
- 新 `ControlPlaneCoordinator` adapter（control client 側）＋ bot `coordinator.backend` selection（未設→Unavailable fail-closed 不變；`"control"`→新 adapter）；LocalCoordinator 標 test-only。
- status.json 加 `held:[{slice_id, reasons}]` 並**穿透** `control.client.read_status()` 與 `/manager status` 顯示（相容測試）。
- start.sh manager 啟動加 `--specs-dir` 指 repo `docs/superpowers/specs`。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `manager-control-plane`: request 型別新增 dispatch（五拒絕路徑＋稽核覆蓋）；status 新增 held backlog 欄位。
- `stage1-core-runtime`: bot coordinator backend selection（fail-closed 預設不變）；`/dispatch` 經 control plane 產真 job。

## Impact

- 受影響碼：`paulshaclaw/control/{contract,client}.py`、`paulshaclaw/coordinator/manager_daemon.py`、`paulshaclaw/core/{daemon,config}.py`、`paulshaclaw/bot/listener.py`、`scripts/start.sh`。
- 相容：done/status additive；既有 tick/fanout 語意不動；cockpit 呈現面另案。
- 依據：`docs/superpowers/specs/2026-07-06-g1-coordinator-adapter-design.md`（含 codex 審查修正）。
