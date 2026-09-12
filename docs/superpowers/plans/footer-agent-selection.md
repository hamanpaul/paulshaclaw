---
work_item: footer-agent-selection
status: accepted
---

# cost footer agy 與安裝時 agent／account 選擇執行計畫

## Tasks

對應 hamanpaul/paulshaclaw#341。建議 branch：`feature/341-footer-agent-selection`。每個 task 先寫 RED 測試再做最小實作；spec 為釘住的 authority。

- [ ] **T1 agy 用量來源調查（時間盒，結論進 tasks.md）**：檢查 `~/.gemini/antigravity-cli/` 與 agy CLI 是否有不需額外 OAuth scope、可釘 schema 的用量／配額來源。有 → 記錄端點、欄位、freshness 判準；無 → 明寫「本輪交付 `source="unknown"`」。不得讀取 `oauth_creds.json`、`antigravity-oauth-token`、`google_accounts.json` 內容。
- [ ] **T2 config 模型**：`AgyProviderConfig`＋`CostConfig.agy`；`ClaudeProviderConfig.enabled`／`CopilotAccountConfig.enabled`；解析器對缺 key 給預設。RED：載入 sample yaml 後 formatter 輸出快照必須與 main 版逐字元相同。
- [ ] **T3 `collect_agy()` 與 formatter**：三種 `source` 的 snapshot 形態與渲染（`N%`／`~N`／`?`／`∞`）；`enabled=false` 或 `None` 不渲染。RED：四個渲染案例＋一個不渲染案例。
- [ ] **T4 `detect_agents()`**：四個 agent 的 which＋路徑存在判定；`_NEVER_READ` 常數；RED：monkeypatch 讓憑證路徑的 `open`／`read_text`／`read_bytes` 拋例外仍能完成偵測。
- [ ] **T5 `--footer` 解析與決策矩陣**：spec 文法（含 `copilot:label:label`、`none`）；TTY／`--plan-only` 判定；report `detected_agents`＋`footer_selection`。RED：`flag`／`skipped(no-tty)`／`skipped(plan-only)` 三案例，以及 `test_clean_venv_runs_deploy_from_installed_wheel_outside_checkout` 不加旗標仍綠且 `mode == "skipped"`。
- [ ] **T6 設定寫回**：deep-merge 只動 `enabled`；備份檔；不存在時以 sample 為底；既有 `label`／`monthly_allowance`／`org` 保留。RED：寫回前後 yaml 除 `enabled` 外 dict 相等、備份檔存在且內容等於寫回前。
- [ ] **T7 TUI**：`footer_select.py`（SelectionList＋per-account 列＋即時預覽）；Pilot RED：toggle→enter 回傳結構、esc 回傳 `None`、未偵測項可勾。
- [ ] **T8 文件**：README §Install、sample yaml `providers.agy` 段與 `enabled` 範例、changelog 碎片。`grep -rn '/home/'` 對新增檔為零命中。
- [ ] **T9 交付**：focused tests → `scripts/preflight-tests.sh` 全綠 → 獨立 review → policy/preflight → PR（`Closes #341`）。tasks.md 末項用 builder 完成語態並勾選。

## Integration gates

- 全套 `scripts/preflight-tests.sh` 綠；policy check 綠（R-09 碎片、R-12 分支名、R-21 零新增 `/home/<user>/`、R-17 `Closes #341`）。
- `tests/test_deploy_template_packaging.py` 全綠（乾淨 venv、無 TTY 路徑不受影響）。
- 獨立 review 對照 spec R1–R8 逐條核對；未處置缺陷為 FAIL；接受的殘餘風險（YAML 註解不保留、agy `unknown`）須在 PR body 明列。
- 部署、發布與本機 config 切換由 operator 整合驗收後執行，不由 worker 自行進行。
