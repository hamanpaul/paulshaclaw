## Context

派工側（`dispatch_ready` #112）與完成側（`complete_tick` #121）皆已具備，但沒有週期 driver。Phase C 以 systemd `--user` timer + oneshot 跑完整 tick，`start.sh` 退成 toggle。完整脈絡見 `docs/superpowers/specs/2026-06-23-persona-manager-phase-c-systemd-design.md` 與 umbrella §4.4/§7/§8。

## Goals / Non-Goals

**Goals:** combined `coordinator tick`（fanout→complete + idle gate）；manager systemd 範本納入 deploy planner；`start.sh` toggle + install 腳本。

**Non-Goals:** Phase D 真實 canary(#123)、enforce 翻牌(#124)、handoff-message schema gate(#131)、retry/requeue 重設計(#132)、動 `route_to_agent`。

## Decisions

- **(a) `run_tick` 放 `manager.py`**：與 `complete_tick` 同模組（manager 職責）；reuse `autonomy.dispatch_ready` + `complete_tick` + `memory.dream.idle.is_idle`（注入 probe）。
- **(b) timer 間隔範本內建預設 300s**：planner render 只替 `__INSTANCE__`；`OnUnitActiveSec=300` 寫死於範本，install 腳本可選以 `PSC_MANAGER_INTERVAL_SECONDS` sed 覆寫（不靠 systemd 原生 env，timer 不支援）。
- **service ExecStart args 由 EnvironmentFile `${PSC_MANAGER_*}` 展開**（systemd 原生支援），故 `-manager.env.tmpl` 的鍵真被使用。
- **(c) 一個 PR 涵蓋 Unit A（tick 命令）→ B（systemd 範本+planner）→ C（start.sh+install）。**
- **fanout 失敗不擋 complete**：`run_tick` 把 `DispatchReadyError`/`RequiresLauncher` 收進 `errors`，仍跑 complete（stage 獨立）。

## Risks / Trade-offs

- [Phase C 即啟 timer 會否誤派工] → fanout 只對 `dispatch:auto∧ready` 派工，現況全 `dispatch:hold` → 不啟 agent；+ `PSC_MANAGER_DISABLED` + `--require-idle` 三層保險。
- [WSL `--user` systemd 不可用] → `start_manager_service()` graceful skip，不破壞既有啟動；開機自啟需 `loginctl enable-linger`（手動驗證）。
- [manager 脫離 tmux 生死] → 刻意取捨（失敗域隔離），需回寫 memory `feedback_operational_preferences`。

## Open Questions

- timer 間隔預設 300s 是否合宜，待本機 journald 觀察後調。
