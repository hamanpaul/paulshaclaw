---
work_item: footer-agent-selection
status: accepted
---

# cost footer 新增 agy 與安裝時 agent／account 選擇

## Requirements

對應 hamanpaul/paulshaclaw#341。

accepted 僅表示規格可執行，不表示程式或驗收已完成。使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。只處理本件 issue；所有實作、測試、OpenSpec、文件及 changelog 限本件 scope。採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為 FAIL，接受風險需明文、有界且可追溯。不得對外送 Telegram、覆寫既有 release、變更共享 service/config。

本 spec 是釘住的 authority：實作不得自行收窄或擴張下列需求；有設計顧慮請在 tasks.md 追認偏差或另開票，不得在本票違背。

### R1 agy provider
- `paulshaclaw/cost/config.py` 新增 `AgyProviderConfig(enabled: bool = False, state_dir: Path = ~/.gemini, label: str = "agy", max_age_seconds: int = 300, local_fallback: bool = False)`，掛在 `CostConfig.agy`；設定路徑 `cost.providers.agy`。缺 key 時使用預設值。
- `paulshaclaw/cost/providers.py` 新增 `collect_agy(config: AgyProviderConfig, *, now: datetime | None = None) -> ProviderSnapshot`。`ProviderSnapshot` 必須帶 `source ∈ {"api", "local_observed", "unknown"}`。
- 可信來源（`source="api"`）只在 T1 研究確認存在「不需額外 OAuth scope、不會觸發 rate limit、schema 可釘」的端點或本機檔時實作；找不到即實作 `source="unknown"`，並在 tasks.md 記錄調查過的候選與結論。`local_observed` 只在 `local_fallback: true` 且有穩定本機 schema 時啟用。
- **禁止讀取**：`~/.gemini/oauth_creds.json`、`~/.gemini/antigravity-cli/antigravity-oauth-token`、`~/.gemini/google_accounts.json` 的內容；本輪 agy 視為單一帳號、以 `label` 顯示，多帳號另開票。

### R2 formatter
- `paulshaclaw/cost/formatter.py` 新增 `agy` 段：`source="api"` → `agy N%`；`local_observed` → `agy ~N`；`unknown` → `agy ?`；`unlimited` → `agy ∞`。warning／critical 著色與 reset 顯示沿用 `cdx`／`cc`／`cpt` 的既有邏輯。
- `enabled=false`、或 collect 回傳 `None` 時，footer **不出現** `agy` 段（不得出現 `agy ?` 佔位）。

### R3 provider／account `enabled` 開關（相容既有設定）
- `ClaudeProviderConfig.enabled: bool = True`、`CopilotAccountConfig.enabled: bool = True` 新增；`CodexProviderConfig.enabled` 既有。
- 既有 config（不含任何新 key）載入後，footer 輸出與變更前逐字元相同；以載入 `paulshaclaw/config/paulshaclaw.sample.yaml` 並比對 formatter 輸出的測試釘住。
- `enabled=false` 的 provider／account 不 collect、不渲染。

### R4 agent 偵測（只看存在，不讀內容）
- 新增 `paulshaclaw/deploy/agents.py`：`detect_agents(*, which=shutil.which, home: Path | None = None) -> tuple[DetectedAgent, ...]`，`DetectedAgent(name, binary: Path | None, state_present: bool)`。
- 偵測矩陣：`codex` → binary `codex` + `~/.codex/auth.json` 存在；`claude` → binary `claude` + `~/.claude/` 存在；`copilot` → binary `copilot` + `~/.config/github-copilot/` 存在；`agy` → binary `agy` + `~/.gemini/` 存在。
- 偵測只允許 `which()` 與 `Path.exists()/is_dir()/is_file()`；測試以 monkeypatch 讓上述路徑的 `open`／`read_text`／`read_bytes` 拋例外，證明偵測路徑零讀取。

### R5 `paulshaclaw deploy install` 的 footer 選擇
- 新旗標 `--footer <spec>`：`spec` 為逗號分隔的 `codex | claude | copilot[:label[:label…]] | agy`，或 `none`。`copilot` 未帶 label 時等於「既有 accounts 全開」。
- 決策矩陣：
  | 條件 | 行為 | report `footer_selection.mode` |
  |---|---|---|
  | 有 `--footer` | 不進 TUI，依 spec 寫回 | `flag` |
  | 無 `--footer`，stdin 與 stdout 皆為 TTY，且非 `--plan-only` | 進 TUI | `tui`（取消時 `cancelled`，config 不動） |
  | 無 `--footer`，任一非 TTY 或 `--plan-only` | 不進 TUI、config 不動 | `skipped`，`reason: "no-tty"` 或 `"plan-only"` |
- report 新增 `detected_agents: [{name, binary, state_present}]`（一律輸出，與是否進 TUI 無關）與 `footer_selection: {mode, enabled: {codex: bool, claude: bool, copilot: {<account_id>: bool}, agy: bool}}`。report 仍為單一 JSON；`--plan-only`／`--verify` 路徑輸出形狀不變。
- `tests/test_deploy_template_packaging.py::test_clean_venv_runs_deploy_from_installed_wheel_outside_checkout` 在不加旗標、無 TTY 下必須維持通過，且 report 含 `footer_selection.mode == "skipped"`。

### R6 設定寫回
- 目標檔為 `--home-dir` 解析出的 `~/.config/paulshaclaw/paulshaclaw.yaml`；不存在時以 sample 為底。
- 寫回前先備份 `paulshaclaw.yaml.bak-<UTC timestamp>`；只改 `cost.providers.{codex,claude,agy}.enabled` 與 `cost.providers.copilot.accounts[].enabled`，其他 key／value 全數保留（deep-merge），既有 `label`／`monthly_allowance`／`org` 不得被洗掉。YAML 註解不保證保留，此限制寫進 README。
- 重跑 install 時，TUI 與 `--footer` 的預設勾選狀態來自既有 config 的 `enabled` 值；未偵測到的 agent 預設不勾但可強制勾選。

### R7 TUI
- `paulshaclaw/deploy/footer_select.py`：textual `App`，一個 `SelectionList` 列 agent（未偵測者顯示 `(未偵測)` 後綴、預設不選），copilot 展開 per-account 列；底部即時預覽一行 footer（用 `formatter` 對合成 snapshot 渲染）；`space` 切換、`enter` 確認、`esc` 取消。
- 以 `App.run_test()` Pilot 測：切換→確認回傳選擇結構；`esc` 回傳 `None`；未偵測項可勾。
- TUI 只做選擇與寫 config；不啟動 daemon、不碰 systemd、不填 secret（`_SECRET_INSTALL_STEPS` 維持手動步驟）。

### R8 文件與變更紀錄
- README §Install 新增 footer 選擇說明（TUI、`--footer` 語法、無 TTY 行為、註解不保留限制）；`paulshaclaw/config/paulshaclaw.sample.yaml` 新增 `providers.agy` 段與 `enabled` 範例；附 `changelog.d/341-footer-agent-selection.md`。

## Acceptance

- [ ] `pytest tests/test_stage8_cost*.py tests/test_deploy_footer_selection.py tests/test_deploy_template_packaging.py -q` 全綠；新增測試覆蓋 R1（三種 source＋enabled=false 不渲染）、R3（sample config 輸出逐字元不變）、R4（零讀取守衛）、R5（三種 mode）、R6（deep-merge 保留欄位＋備份檔）、R7（Pilot 三情境）。
- [ ] 有 agy 的機器 `python -m paulshaclaw.cost --no-refresh`（或既有 footer 入口）在 `agy.enabled: true` 時出現 `agy` 段；`enabled: false` 或無 agy 時不出現。
- [ ] `paulshaclaw deploy install --plan-only ... </dev/null` 的 JSON report 含 `detected_agents` 與 `footer_selection.mode == "skipped"`；`--footer codex,agy` 寫回後 yaml 只有 `enabled` 欄位變動、備份檔存在。
- [ ] 全套 `scripts/preflight-tests.sh` 綠；policy／preflight 通過；PR body `Closes #341`。
