---
type: change
scope: cost
issue: 341
---

### Changed

- deploy install / upgrade 新增 footer agent/account 選擇：支援 `--footer codex,claude,copilot[:label...],agy,none`、SelectionList TUI、`detected_agents` / `footer_selection` JSON report，以及只改 `enabled` 的 config write-back / backup / sample fallback。
- Stage 8 cost footer 新增 agy provider 骨架與 `enabled` flags：`cost.providers.agy`、Claude provider `enabled`、Copilot account `enabled` 均可由 config 控制，agy 啟用後會依 snapshot 顯示 `N%` / `~N` / `?` / `∞`。
