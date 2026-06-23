# Tasks

> 詳細逐步 TDD 見 `docs/superpowers/plans/2026-06-23-persona-manager-phase-c.md`。本檔為 apply 追蹤用高階 checklist。

## 1. Unit A — combined `coordinator tick`

- [x] 1.1 `tests/test_coordinator_manager.py` 加 `run_tick` failing tests（idle skip / idle 達標跑 fanout+complete / fanout 例外不擋 complete）（RED）
- [x] 1.2 `manager.py` 加 `run_tick`（reuse `dispatch_ready` + `complete_tick` + `memory.dream.idle.is_idle`，fanout 例外收進 errors），GREEN
- [x] 1.3 CLI `tick` 子命令 failing test（`--require-idle --max-load 0` → skipped）（RED）
- [x] 1.4 `cli.py` 加 `tick` 子命令，GREEN
- [x] 1.5 commit

## 2. Unit B — systemd 範本 + planner

- [x] 2.1 建 `__INSTANCE__-manager.service.tmpl`（oneshot + ExecStart coordinator tick + EnvironmentFile）
- [x] 2.2 建 `__INSTANCE__-manager.timer.tmpl`（OnBootSec + OnUnitActiveSec=300 + WantedBy=timers.target）
- [x] 2.3 建 `__INSTANCE__-manager.env.tmpl`（PSC_MANAGER_SPECS_DIR/EXECUTOR/INTERVAL_SECONDS）
- [x] 2.4 `test_stage7_deploy_three_plane.py` 加 manager 範本斷言（relpath/target/內容）（RED）
- [x] 2.5 `planner.py` `_TEMPLATE_CATALOG` += 3 entries，GREEN
- [x] 2.6 commit

## 3. Unit C — start.sh toggle + install 腳本

- [x] 3.1 `scripts/start.sh` 加 `start_manager_service()`（PSC_MANAGER_DISABLED / systemctl 不可用 graceful skip）+ `cleanup()` stop
- [x] 3.2 建 `scripts/coordinator/install-manager-units.sh`（render→copy→daemon-reload→enable；提示 enable-linger）
- [x] 3.3 以 stub `systemctl`（PATH 注入）做 graceful-skip / toggle 的 bash 斷言（最小 smoke）
- [x] 3.4 commit

## 4. 驗證與收尾

- [x] 4.1 跑 coordinator + persona + stage7 deploy 套件，確認無回歸
- [x] 4.2 跑完整 `tests/` + `paulshaclaw/memory/tests/`
- [x] 4.3 WSL `--user` lingering 手動驗證項記錄（文件化，不阻 PR）
- [x] 4.4 進 code review gate（`/codex:adversarial-review`）
- [x] 4.5 回寫 memory（manager 走 systemd、不隨 tmux 重啟）
