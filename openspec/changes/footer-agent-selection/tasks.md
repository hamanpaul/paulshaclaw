## 1. --footer 選擇與回報

- [x] 1.1 RED：install / installed-wheel regression 覆蓋 `--footer` flag、`skipped(no-tty)`、`skipped(plan-only)`，並要求 report 含 `detected_agents` 與 `footer_selection`
- [x] 1.2 GREEN：實作 `--footer` 解析與決策矩陣，讓 plan-only、無 TTY 與顯式旗標都回報正確 footer selection
- [x] 1.3 GREEN：補上 conftest 的 deploy 測試模組前綴，讓 footer selection 回歸測試受家目錄隔離防線保護

## 2. builder recovery card（本 worktree）

- [x] 2.1 agy footer scope：對齊 `AgyProviderConfig(enabled, state_dir, label, max_age_seconds, local_fallback)` 與 `collect_agy(config, *, now)`；Claude provider `enabled`、Copilot account `enabled` 仍由 config 控制。
  - T1 調查結論：本 card 只把 `~/.gemini/antigravity-cli/state.json` 視為本地 fallback 候選，不把它綁成可釘 schema 的官方 quota endpoint，也不讀取任何 OAuth/帳號檔內容；因此預設維持 `local_fallback=false`，未提供可信來源時回報 `source="unknown"`／footer `agy ?`。
- [x] 2.2 cost render/collect：實作 `collect_agy()` 與 footer `agy` 渲染，涵蓋 `N%` / `~N` / `?` / `∞`，並讓 disabled provider/account 不進最終 footer。
- [x] 2.3 deploy footer plumbing：新增 `paulshaclaw/deploy/agents.py`，處理 `_NEVER_READ` 偵測、`copilot:label:label` / `codex,agy` / bare `copilot` 文法、structured report 與 config write-back。
- [x] 2.4 SelectionList TUI：新增 `paulshaclaw/deploy/footer_select.py`，支援 toggle→enter 結構化回傳、esc 取消、未偵測項仍可勾選與即時 preview。
- [x] 2.5 docs/tests：更新 README、sample config、changelog fragment，並新增 `tests/test_deploy_footer_selection.py` / `tests/test_footer_agent_selection_cost.py` focused coverage。
- [x] 2.6 repair follow-up：補齊 reviewer/Manager 指出的 Candidate 偏差：`--footer` parse／label 錯誤改為單一 JSON failure report 且不落盤、`detect_agents()` 對齊 `DetectedAgent(name,binary,state_present)` 契約、未偵測項改用 `"(未偵測)"` 並預設不勾選、`ProviderSnapshot.source` 與 `AgyProviderConfig.state_dir`／`collect_agy(..., now=None)` 對齊 spec。
- [x] 2.7 final pre-archive repair：對齊 R2 字面，讓 `source="local_observed"` 的 agy footer 輸出 `agy ~N`（不是 `agy N%`），並更新 focused 測試；archive、全套 preflight、PR 與關 issue 仍由 Manager / operator 後續執行。
- [x] 2.8 coverage-only follow-up：補 `tests/test_footer_agent_selection_cost.py` 的 `source="api"` + `percent_used` 直接斷言，讓 T3 的 `N%` / `~N` / `?` / `∞` 四種 agy 形態各有獨立測試；不變更 runtime 行為，archive／PR／關 issue 仍由 Manager / operator 後續執行。
