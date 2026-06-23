---
dispatch: hold
slice_id: persona-manager-phase-c
plan: null
depends_on: [persona-manager-complete-tick]
---

# Persona Manager Phase C — systemd 常駐 manager（#122）設計

> 日期：2026-06-23 ｜ 狀態：草案（待覆審）｜ 分支：`feature/122-phase-c-systemd`
> 上游：umbrella `2026-06-22-persona-manager-daemon-design.md` §2/§4.4/§7/§8；完成側 `2026-06-23-persona-manager-complete-tick-design.md`（#121，已 merge）。
> Issue：#122（umbrella #14；依賴 #121）。

## 1. 背景與校正

#121 落地完成側 `complete_tick`，但 manager 仍只能手動 CLI 跑。Phase C 目標：以 systemd `--user` timer + oneshot 週期跑**完整 tick**（fanout→complete，idle-gated），`start.sh` 退成 `systemctl --user start/stop` 的 toggle，manager 不再隨 tmux 生死。

派工側 `dispatch_ready`（#112）與完成側 `complete_tick`（#121）都已具備，缺的是：把兩者合成一支 `coordinator tick`、包成 systemd oneshot+timer、由 deploy 平面與 start.sh 接線。

## 2. 目標與非目標

**目標**
- 新增 combined `coordinator tick`（fanout→complete 一趟，`--require-idle` 沿用 dream idle gate）。
- 新增 manager systemd 範本（oneshot service + timer + runtime env），納入 deploy planner。
- `start.sh` 加 `start_manager_service()`（toggle，graceful skip）+ `cleanup()` stop。
- `install-manager-units.sh`（render→copy→daemon-reload→enable）。

**非目標**
- ❌ 第一個真實 `dispatch:auto` 端到端（Phase D #123）。
- ❌ enforce 翻牌（#124）、handoff-message schema gate（#131）、retry/requeue manifest 重設計（#132）。
- ❌ 動互動路徑（`route_to_agent`）。

## 3. 組件設計

### 3.1 Unit A — combined `coordinator tick`（決策 a：放 `manager.py`）

`manager.run_tick(dispatcher, *, metas, launcher, persona="builder", is_satisfied, gate_runner=None, handoff_dir=autonomy.DEFAULT_HANDOFF_DIR, require_idle=False, max_load=1.0, idle_probe=os.getloadavg, clock=_utcnow) -> dict`

1. `require_idle and not idle.is_idle(max_load, idle_probe)` → 回 `{"skipped": "not-idle", "dispatched": [], "completed": [], "errors": []}`。
2. fanout：`autonomy.dispatch_ready(metas, is_satisfied, dispatcher, persona, launcher=launcher)`；**例外（`DispatchReadyError`/`DispatchReadyRequiresLauncherError`）收進 `errors`，不中斷**。
3. complete：reuse `complete_tick(dispatcher, gate_runner=, handoff_dir=, metas=)`。
4. 回 `{"skipped": False, "dispatched": [...], "completed": [...], "errors": [...]}`。

reuse `paulshaclaw.memory.dream.idle.is_idle`（注入 `idle_probe` 求測試決定性）。CLI `tick` 子命令：`--specs-dir`(必)/`--executor`/`--handoff-dir`/`--require-idle`/`--max-load`，與 `fanout` 同構建 dispatcher+launcher。

### 3.2 Unit B — systemd 範本 + planner

| 範本 | 重點 |
|---|---|
| `templates/core/systemd/__INSTANCE__-manager.service.tmpl` | `Type=oneshot`；EnvironmentFile 比照 telegram（`__INSTANCE__.env` + `__INSTANCE__-manager.env`）；`ExecStart=/usr/bin/env python3 -m paulshaclaw.coordinator tick --require-idle --specs-dir ${PSC_MANAGER_SPECS_DIR} --executor ${PSC_MANAGER_EXECUTOR}`（**args 由 EnvironmentFile 的 `${PSC_MANAGER_*}` 展開**，systemd 原生支援，故 env.tmpl 的鍵真的被用到） |
| `templates/core/systemd/__INSTANCE__-manager.timer.tmpl` | `OnBootSec=2min` + `OnUnitActiveSec=300`（**決策 b：範本內建預設**）；`[Install] WantedBy=timers.target` |
| `templates/core/runtime/__INSTANCE__-manager.env.tmpl` | `PSC_INSTANCE`/`PSC_PLANE=core`/`PSC_MANAGER_SPECS_DIR`/`PSC_MANAGER_EXECUTOR`/`PSC_MANAGER_INTERVAL_SECONDS` |

planner `_TEMPLATE_CATALOG` += 3 entries（plane=core，rename「以 __INSTANCE__ 取代實例名並移除 .tmpl」）；`test_stage7_deploy_three_plane.py` 補斷言（assets 數、新 relpath、範本內容字串）。

### 3.3 Unit C — start.sh toggle + install 腳本

- `scripts/start.sh` `start_manager_service()`：
  - `PSC_MANAGER_DISABLED=1` → skip + log。
  - `systemctl --user` 不可用（`command -v systemctl` 失敗或 `systemctl --user` 無回應，WSL 無 user systemd）→ **graceful skip + log，不影響既有啟動**。
  - 否則 `systemctl --user start <instance>-manager.timer`。
  - `cleanup()` 加 `systemctl --user stop <instance>-manager.timer 2>/dev/null || true`。
  - **start.sh 不擁有 manager 進程**（與 cost/dream 背景 loop 不同）。
- `scripts/coordinator/install-manager-units.sh`：render（替 `__INSTANCE__`、可選以 `PSC_MANAGER_INTERVAL_SECONDS` sed 覆寫 `OnUnitActiveSec`）→ copy `~/.config/systemd/user/` → `systemctl --user daemon-reload` → `enable --now <instance>-manager.timer`；偵測並提示 `loginctl enable-linger paul_chen`（WSL 開機自啟需）。

## 4. 安全性 — Phase C ≠ 真派工

fanout 只對 `dispatch:auto ∧ ready` 單位派工；目前所有 spec frontmatter 為 `dispatch: hold`，故 timer 跑起來找不到就緒單位＝**不會真啟 agent**。第一個真實 dispatch 是 Phase D(#123) canary（把某 slice 標 `dispatch:auto`）。三層保險：`dispatch:hold` 預設 + `PSC_MANAGER_DISABLED` + `--require-idle`。

## 5. 錯誤處理（fail-safe / stage 獨立）

- fanout 失敗 → 收進 `errors`，仍跑 complete（完成側不被派工側連累）。
- idle 未達 → 整趟 skip，非錯誤（journald 留一行）。
- systemctl 不可用 → start.sh skip，不破壞 telegram/cockpit 啟動。

## 6. 測試

- `tests/test_coordinator_manager.py`（擴）：`run_tick` fanout+complete 串接；`--require-idle` 注入 high-load probe → `skipped`；fanout 拋例外 → 進 `errors` 且 complete 仍跑。
- `tests/test_coordinator_cli_*`：`tick` 子命令 smoke。
- `tests/test_stage7_deploy_three_plane.py`（擴）：3 新範本存在 + 內容（`Type=oneshot`、`ExecStart ... coordinator tick`、`OnUnitActiveSec`、`WantedBy=timers.target`、env 鍵）。
- start.sh / install：以 stub `systemctl`（PATH 注入假 binary）做 graceful-skip 與 toggle 的 bash 斷言；WSL `--user` lingering 手動驗證（文件化）。

## 7. 影響檔案

| 檔案 | 動作 |
|---|---|
| `paulshaclaw/coordinator/manager.py` | Modify（加 `run_tick` + `_utcnow` reuse） |
| `paulshaclaw/coordinator/cli.py` | Modify（加 `tick` 子命令） |
| `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.service.tmpl` | Create |
| `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.timer.tmpl` | Create |
| `paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-manager.env.tmpl` | Create |
| `paulshaclaw/deploy/planner.py` | Modify（catalog += 3） |
| `scripts/start.sh` | Modify（`start_manager_service` + cleanup） |
| `scripts/coordinator/install-manager-units.sh` | Create |
| `tests/test_coordinator_manager.py` / `test_coordinator_cli_*` / `test_stage7_deploy_three_plane.py` | Modify/Create |

## 8. 收尾

- 回寫 memory：`feedback_operational_preferences`（補註 manager 走 systemd、刻意不隨 tmux 重啟，換失敗域隔離）、`project_stage2_install_state`（新增 manager timer 安裝狀態）。
- 一個 PR 涵蓋 Unit A→B→C（決策 c）。
