## Why

#121 落地完成側 `complete_tick`，但 manager 仍只能手動 CLI 跑、且綁 tmux 生死。Phase C(#122) 要讓 manager 以 systemd `--user` timer + oneshot 週期跑**完整 tick**（fanout→complete，idle-gated），`start.sh` 退成 toggle，manager 改由 systemd 持有——失敗域與 tmux 解耦。此為「persona 通電」epic（#14）讓 fan-out 自行週期推進的關鍵，也是 Phase D canary(#123) 的前置。

## What Changes

- 新增 combined `coordinator tick`：一支 `manager.run_tick(...)` 跑 fanout（`dispatch_ready`）→ `complete_tick` 一趟；`--require-idle` 沿用 `memory.dream.idle.is_idle`（1-min load gate）；fanout 例外收進 summary 不中斷 complete。
- `coordinator` CLI 新增 `tick` 子命令（`--specs-dir`/`--executor`/`--handoff-dir`/`--require-idle`/`--max-load`）。
- 新增 manager systemd 範本：`__INSTANCE__-manager.service.tmpl`（`Type=oneshot`，ExecStart 由 EnvironmentFile `${PSC_MANAGER_*}` 展開）、`__INSTANCE__-manager.timer.tmpl`（`OnBootSec`+`OnUnitActiveSec=300` 預設）、`__INSTANCE__-manager.env.tmpl`；納入 deploy planner `_TEMPLATE_CATALOG`。
- `scripts/start.sh` 加 `start_manager_service()`（`PSC_MANAGER_DISABLED` / systemctl 不可用 graceful skip）+ `cleanup()` stop；start.sh 不擁有 manager 進程。
- 新增 `scripts/coordinator/install-manager-units.sh`（render→copy `~/.config/systemd/user/`→daemon-reload→enable --now timer；提示 `loginctl enable-linger`）。

## Capabilities

### New Capabilities

- `coordinator-tick`: combined manager tick——`run_tick` 跑 fanout→complete 一趟，`--require-idle` 以 1-min load average gate（reuse dream idle probe，可注入），fanout 失敗不連累 complete。

### Modified Capabilities

- `coordinator-cli`: 新增 `tick` 子命令（建 Dispatcher + 選用 launcher → `run_tick` → 印 summary JSON）。
- `stage7`: 三分部署 template catalog 新增 manager systemd units（service oneshot / timer / runtime env），沿用 `__INSTANCE__` rename 規則，目標檔名 `<instance>-manager.{service,timer}`。

## Impact

- 代碼：修改 `paulshaclaw/coordinator/{manager.py,cli.py}`、`paulshaclaw/deploy/planner.py`、`scripts/start.sh`；新增 3 個 systemd 範本、`scripts/coordinator/install-manager-units.sh`；新增/修改對應 tests。
- 設計依據：`docs/superpowers/specs/2026-06-23-persona-manager-phase-c-systemd-design.md`。
- 安全：Phase C ≠ 真派工——fanout 只對 `dispatch:auto ∧ ready` 派工，目前 spec 皆 `dispatch:hold`，故 timer 跑起來不啟 agent；真實 dispatch 留 Phase D(#123)。三層保險：`dispatch:hold` + `PSC_MANAGER_DISABLED` + `--require-idle`。
- WSL `--user` lingering（`loginctl enable-linger`）需手動驗證（開機自啟）。
- 收尾回寫 memory：manager 走 systemd、刻意不隨 tmux 重啟。
- 不動互動路徑（`route_to_agent`）；留 Phase D(#123)、#124/#131/#132。
