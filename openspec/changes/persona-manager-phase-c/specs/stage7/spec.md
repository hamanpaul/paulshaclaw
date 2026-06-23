## ADDED Requirements

### Requirement: Manager systemd 範本納入三分部署 catalog

Stage 7 三分部署 template 清單 MUST 涵蓋 manager 常駐單元：`core/systemd/__INSTANCE__-manager.service.tmpl`（`Type=oneshot`；以 `Environment=PSC_MANAGER_SPECS_DIR=%h/...`（unit 內 specifier 展開）提供 specs 路徑，以 EnvironmentFile 提供 `PSC_MANAGER_EXECUTOR`；ExecStart 以 `python3 -m paulshaclaw.coordinator tick --require-idle --specs-dir ${PSC_MANAGER_SPECS_DIR} --executor ${PSC_MANAGER_EXECUTOR}` 展開）、`core/systemd/__INSTANCE__-manager.timer.tmpl`（含 `OnBootSec` 與 `OnUnitActiveSec`、`Unit=` 指回 service、`[Install] WantedBy=timers.target`）、`core/runtime/__INSTANCE__-manager.env.tmpl`（含 `PSC_MANAGER_EXECUTOR`/`PSC_MANAGER_INTERVAL_SECONDS`）。三者 MUST 沿用 `__INSTANCE__` 取代 + 移除 `.tmpl` 的 rename 規則，目標檔名 MUST 為 `<instance>-manager.service` / `<instance>-manager.timer` / `<instance>-manager.env`，使 manager 可獨立 enable/restart 而不影響 core/telegram service。

#### Scenario: catalog 涵蓋 manager service/timer/env 且 rename 正確

- **WHEN** 操作者列出 `install` plan 的 template 資產
- **THEN** assets MUST 含上述三個 manager 範本 relpath，且各自 `target_path` MUST 以 `<instance>-manager.service` / `.timer` / `-manager.env` 結尾

#### Scenario: manager service 為 oneshot 且 ExecStart 走 coordinator tick

- **WHEN** 讀取 `__INSTANCE__-manager.service.tmpl` 範本內容
- **THEN** MUST 含 `Type=oneshot` 與 `ExecStart=` 引用 `-m paulshaclaw.coordinator tick`，timer 範本 MUST 含 `OnUnitActiveSec` 與 `WantedBy=timers.target`
