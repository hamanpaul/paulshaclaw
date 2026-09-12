---
type: fix
scope: launcher
issue: 346
---
`paulshaclaw` 指令（release 啟動路徑）的 cortex fallback（monitor／manager）若起不來、或啟動前就退出，不再 fail-closed 擋下整個 cockpit：改為記錄 degraded 啟動、於 stderr 印出警告與對應 log 路徑（`cortex-monitor.log`／`cortex-manager.log`），cockpit 退出後再印一次摘要（避免被 TUI 全螢幕蓋掉），cockpit（或 `--no-cockpit` 下常駐前景的 operator shell）仍照常啟動。僅限 release 路徑：dev 路徑 `scripts/start.sh` 的 `verify_cortex_fallback_alive` 未變、仍 fail-closed。release 路徑其他 fail-closed 條款（start lock 接管、telegram 半套設定、`run_cockpit` 缺 TMUX_PANE）不變。
