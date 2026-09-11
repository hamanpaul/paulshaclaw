## 1. --footer 選擇與回報

- [x] 1.1 RED：install / installed-wheel regression 覆蓋 `--footer` flag、`skipped(no-tty)`、`skipped(plan-only)`，並要求 report 含 `detected_agents` 與 `footer_selection`
- [x] 1.2 GREEN：實作 `--footer` 解析與決策矩陣，讓 plan-only、無 TTY 與顯式旗標都回報正確 footer selection
- [x] 1.3 GREEN：補上 conftest 的 deploy 測試模組前綴，讓 footer selection 回歸測試受家目錄隔離防線保護

## 2. builder recovery card（本 worktree）

- [x] 2.1 agy footer scope：補上 `AgyProviderConfig` / `CostConfig.agy`、Claude provider `enabled`、Copilot account `enabled`；agy 用量來源依計畫保守落在 `source="unknown"` fallback。
- [x] 2.2 cost render/collect：實作 `collect_agy()` 與 footer `agy` 渲染，涵蓋 `N%` / `~N` / `?` / `∞`，並讓 disabled provider/account 不進最終 footer。
- [x] 2.3 deploy footer plumbing：新增 `paulshaclaw/deploy/agents.py`，處理 `_NEVER_READ` 偵測、`copilot:label:label` / `codex,agy` / bare `copilot` 文法、structured report 與 config write-back。
- [x] 2.4 SelectionList TUI：新增 `paulshaclaw/deploy/footer_select.py`，支援 toggle→enter 結構化回傳、esc 取消、未偵測項仍可勾選與即時 preview。
- [x] 2.5 docs/tests：更新 README、sample config、changelog fragment，並新增 `tests/test_deploy_footer_selection.py` / `tests/test_footer_agent_selection_cost.py` focused coverage。
- [ ] 2.6 archive / PR / ship：本 builder card 不執行 archive、policy/preflight、PR 或關 issue 流程。
