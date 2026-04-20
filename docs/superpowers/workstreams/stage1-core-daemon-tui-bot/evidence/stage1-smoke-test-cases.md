# Stage 1 smoke test cases

1. `daemon-status`
   - 目標：確認 daemon 可載入設定並回傳最小狀態。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_daemon_loads_config_and_returns_status -v`
2. `config-env-fallback`
   - 目標：確認 `PSC_STAGE1_CONFIG` 可作為設定來源。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_load_config_supports_env_fallback -v`
3. `coordinator-dispatch`
   - 目標：確認 `/dispatch <task>` 會建立最小 coordinator job。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_dispatch_command_calls_coordinator -v`
4. `tui-pane-map`
   - 目標：確認 TUI 可列出 pane / task 對照。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_tui_view_lists_panes_and_tasks -v`
5. `telegram-auth`
   - 目標：確認未授權使用者被拒、授權使用者可讀取狀態。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_telegram_router_rejects_unauthorized_user -v`
6. `cli-entry`
   - 目標：確認 `python -m paulshaclaw.core.daemon` 可輸出 JSON 狀態。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_cli_entry_outputs_json_status -v`
7. `cli-env-config`
   - 目標：確認 CLI 在未帶 `--config` 時可透過 `PSC_STAGE1_CONFIG` 啟動。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_cli_entry_supports_env_config -v`
8. `telegram-invalid-command`
   - 目標：確認授權使用者輸入未知指令時，bot 會回傳明確錯誤而不是直接拋例外。
   - 命令：`python -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_telegram_router_surfaces_invalid_command -v`
