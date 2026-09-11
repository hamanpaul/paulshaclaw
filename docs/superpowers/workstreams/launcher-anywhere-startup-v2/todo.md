---
work_item: launcher-anywhere-startup-v2
---

# launcher-anywhere-startup-v2 / todo

對應 issue：`hamanpaul/paulshaclaw#334`。

## Current Sprint

- [ ] built wheel 必須包含 `paulshaclaw/core/commands.json`，先以 wheel-content RED test 重現
- [ ] launcher 必須以 kernel flock 辨識 `~/.agents/control/cortex/manager.lock`，不得誤起 fallback manager
- [ ] `paulshaclaw --no-cockpit` 與既有 `paulshaclaw up --no-cockpit` 必須相容
- [ ] 禁止把 runtime 驗收狀態 `ready`／`clean-stop` 新增成 CLI subcommand
- [ ] 依 `openspec/changes/launcher-anywhere-startup-v2/` 執行 RED → 最小修正 → full tests → Spark review → archive → local commit
- [ ] 重建並 force-reinstall pipx wheel；從 `/tmp` 與第二個非 repo 目錄驗證 installed `paulshaclaw` ready 與乾淨停止

## Model Contract

- planner：`codex / gpt-5.6-luna`（max）
- builder：`agy / gemini-3.7-flash-high`（high）
- reviewer：`codex / gpt-5.3-codex-spark`（xhigh）

## Review Gate

- 三個已證實根因任一未有 RED test 與 production fix，即 FAIL。
- source-tree import、`--help`、安裝成功均不能替代 installed-runtime live proof。
- 詳細 proposal/design/spec/tasks 以 apply-ready OpenSpec change 為權威。
