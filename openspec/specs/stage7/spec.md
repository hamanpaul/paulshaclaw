# stage7 Specification

## Purpose

Stage 7 SHALL 建立三分部署 baseline，將部署物拆成 `core`、`state`、`secret` 三個 plane，並以最小可驗證流程提供 `install` / `upgrade` / `uninstall` 命令骨架、template rename 規則、state/secret 權限檢查、secret install 互動步驟，以及 rollback 檢查點與還原策略。
## Requirements
### Requirement: 三分部署命令骨架

Stage 7 MUST 提供 `install`、`upgrade`、`uninstall` 三個命令骨架。每個命令 MUST 產生可檢查的部署 plan，至少包含：`command`、`instance_name`、`root_dir`、`templates`、`steps`、`rollback_checkpoints`、`rollback_actions`。  
`upgrade` 與 `uninstall` MUST 明確標示 `preserve-state` 與 `preserve-secret`，避免覆寫或刪除非 core plane。

#### Scenario: CLI 可輸出 install/upgrade/uninstall plan

- **WHEN** 操作者執行 `python3 -m paulshaclaw.deploy install --instance demo-agent --root-dir /tmp/demo`、`upgrade` 與 `uninstall`
- **THEN** 每個命令 MUST 成功輸出 JSON plan，且 plan 內 MUST 包含 templates 與 rollback checkpoints

### Requirement: Template 檔清單與 rename 規則

Stage 7 MUST 維護三分部署 template 清單，至少覆蓋：
- core systemd unit
- core env
- Telegram systemd unit
- Telegram runtime env
- state config
- secret bootstrap env
- Telegram secret env

Template rename 規則 MUST 支援 `__INSTANCE__` 取代為實例名，且 MUST 移除 `.tmpl` 後綴，讓目標檔名可直接落到部署目錄。Telegram systemd unit 的目標檔名 MUST 使用 `<instance>-telegram.service`，以便獨立 restart bot listener 而不重啟 core service。

#### Scenario: template 資產涵蓋 core/state/secret 與 Telegram service

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage7_deploy_three_plane.TemplateMappingTests -v`
- **THEN** 測試 MUST 驗證 template 清單至少含七個檔案、plane 集合為 `core/state/secret`，且每個 template 實體檔案存在

#### Scenario: rename 規則可產生最終目標檔名

- **WHEN** 操作者以 `core/systemd/__INSTANCE__.service.tmpl` 套用 instance `demo-agent`
- **THEN** 目標路徑 MUST 轉成 `core/systemd/demo-agent.service`

#### Scenario: Telegram unit rename 規則產生獨立 service 名稱

- **WHEN** 操作者以 `core/systemd/__INSTANCE__-telegram.service.tmpl` 套用 instance `demo-agent`
- **THEN** 目標路徑 MUST 轉成 `core/systemd/demo-agent-telegram.service`

### Requirement: state 與 secret 權限檢查

Stage 7 MUST 對 `state` 與 `secret` plane 提供 fail-closed 權限檢查。  
`state` plane MUST 拒絕 group writable 與任何 other 權限。  
`secret` plane MUST 僅允許 owner 權限，基線為 `0700/0600`。

#### Scenario: 不安全權限會被拒絕

- **WHEN** 操作者驗證 `state=0777` 或 `secret=0750`
- **THEN** 檢查結果 MUST 回傳 `allowed=false`，且 reason MUST 指出對應 plane 與拒絕原因

#### Scenario: 安全權限可通過

- **WHEN** 操作者驗證 `state=0750` 與 `secret=0700`
- **THEN** 檢查結果 MUST 回傳 `allowed=true`

### Requirement: secret install 互動步驟

Stage 7 MUST 定義最小可驗證的 secret install 互動流程，至少包含：
- 輸入 secret 來源（私有 repo 或離線封裝）
- 確認 secret plane 目標目錄
- 確認將以 `0700/0600` 權限建立

流程完成後 MUST 回傳 `secret-preflight` 與 `secret-installed` 兩個 checkpoint。若未確認權限，流程 MUST 拒絕繼續。

#### Scenario: 未確認權限時 secret install 失敗

- **WHEN** 操作者提供 `permission_ack=no`
- **THEN** 流程 MUST 拋出錯誤並指出需確認 `0700/0600` 權限

#### Scenario: 私有 repo secret install 產生 checkpoint 摘要

- **WHEN** 操作者提供私有 repo source、目標路徑與 `permission_ack=yes`
- **THEN** 回傳摘要 MUST 包含 `source_kind=private-repo`、`plane=secret`、`secret-preflight` 與 `secret-installed`

### Requirement: rollback 還原策略與檢查點

Stage 7 MUST 為 `install`、`upgrade`、`uninstall` 三個命令定義 rollback checkpoint 與 restore 動作。  
`install` MUST 包含至少 `pre-install`、`post-core-render`、`post-state-init`、`post-secret-install`。  
`upgrade` MUST 在還原策略中保留 `preserve-state` 與 `preserve-secret`。  
`uninstall` MUST 只移除 core plane，並以 rollback plan 保留 `state`/`secret`。

#### Scenario: 三個命令都具有 rollback baseline

- **WHEN** 操作者執行 `python3 -m unittest tests.test_stage7_deploy_three_plane.CommandPlanTests -v`
- **THEN** 測試 MUST 驗證三個命令皆至少有一個 checkpoint 與 restore 動作，且 `upgrade` / `uninstall` 的 rollback action 內含 `preserve-state` 與 `preserve-secret`

### Requirement: Stage 7 證據與文件收斂

Stage 7 MUST 將 red/green/final 測試輸出保留在 `docs/superpowers/workstreams/stage7-deploy-three-plane/evidence/`，並同步更新 `task.md`、`plan.md`、`todo.md`、`review.md` 以反映完成狀態、風險與 handoff。  
Stage 7 文件 MUST 不修改 Stage 5 專屬的 `docs/ops/recovery.md`。

#### Scenario: TDD 證據存在且可追溯

- **WHEN** 審查者檢查 Stage 7 evidence 目錄
- **THEN** 目錄 MUST 至少包含 red、green 與 final discover 三類輸出，以及 TDD 摘要

### Requirement: Local startup applies Stage 8 cost footer

Stage 7 SHALL ensure local startup can apply the Stage 8 cost footer to the current tmux session before launching the Stage 11 cockpit. The startup path MUST use session-local tmux options, MUST set `status-interval` to the configured Stage 8 refresh interval, MUST preserve any existing `status-right` value, and MUST NOT modify global `~/.tmux.conf`.

#### Scenario: Startup preserves existing status-right

- **WHEN** `scripts/start.sh` runs inside tmux and the current session already has a `status-right` value
- **THEN** the script MUST append or wrap the Stage 8 footer command without discarding the existing value

#### Scenario: Startup avoids global tmux config

- **WHEN** `scripts/start.sh` applies the Stage 8 footer
- **THEN** it MUST use session-local tmux settings rather than global `tmux set-option -g`
- **THEN** it MUST NOT write to `~/.tmux.conf`

### Requirement: Manager systemd 範本納入三分部署 catalog

Stage 7 三分部署 template 清單 MUST 涵蓋 manager 常駐單元：`core/systemd/__INSTANCE__-manager.service.tmpl`（`Type=oneshot`；以 `Environment=PSC_MANAGER_SPECS_DIR=%h/...`（unit 內 specifier 展開）提供 specs 路徑，以 EnvironmentFile 提供 `PSC_MANAGER_EXECUTOR`；ExecStart 以 `python3 -m paulshaclaw.coordinator tick --require-idle --specs-dir ${PSC_MANAGER_SPECS_DIR} --executor ${PSC_MANAGER_EXECUTOR}` 展開）、`core/systemd/__INSTANCE__-manager.timer.tmpl`（含 `OnBootSec` 與 `OnUnitActiveSec`、`Unit=` 指回 service、`[Install] WantedBy=timers.target`）、`core/runtime/__INSTANCE__-manager.env.tmpl`（含 `PSC_MANAGER_EXECUTOR`/`PSC_MANAGER_INTERVAL_SECONDS`）。三者 MUST 沿用 `__INSTANCE__` 取代 + 移除 `.tmpl` 的 rename 規則，目標檔名 MUST 為 `<instance>-manager.service` / `<instance>-manager.timer` / `<instance>-manager.env`，使 manager 可獨立 enable/restart 而不影響 core/telegram service。

#### Scenario: catalog 涵蓋 manager service/timer/env 且 rename 正確

- **WHEN** 操作者列出 `install` plan 的 template 資產
- **THEN** assets MUST 含上述三個 manager 範本 relpath，且各自 `target_path` MUST 以 `<instance>-manager.service` / `.timer` / `-manager.env` 結尾

#### Scenario: manager service 為 oneshot 且 ExecStart 走 coordinator tick

- **WHEN** 讀取 `__INSTANCE__-manager.service.tmpl` 範本內容
- **THEN** MUST 含 `Type=oneshot` 與 `ExecStart=` 引用 `-m paulshaclaw.coordinator tick`，timer 範本 MUST 含 `OnUnitActiveSec` 與 `WantedBy=timers.target`

