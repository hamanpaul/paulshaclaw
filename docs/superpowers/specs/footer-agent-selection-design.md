---
work_item: footer-agent-selection
status: accepted
---

# cost footer agy 與安裝時 agent／account 選擇設計

## Decisions

對應 hamanpaul/paulshaclaw#341。accepted 僅表示規格可執行，不表示程式或驗收已完成。

- **D1 偵測只證明「存在」**：`detect_agents()` 只用 `shutil.which` 與 `Path.exists()`；不讀任何登入態檔案內容。理由：repo 為 public、R-21 去識別化規則生效中，且 footer 選擇不需要憑證資訊。憑證路徑清單寫死在 `agents.py` 常數 `_NEVER_READ`，測試以 monkeypatch 守衛。
- **D2 agy 用量來源 fail-closed**：`~/.gemini/state.json` 只有 `tipsShown`／`startupWarningCounts`，`antigravity-cli/` 無 quota 檔，`agy --help` 無 usage 子命令（2026-09-11 實查）。因此 `collect_agy()` 先以 `source` 欄位區分三種形態，T1 研究若找不到可信端點就交付 `unknown`（footer `agy ?`），不得用估算冒充百分比。`local_observed` 只在 `local_fallback: true` 且 schema 穩定時啟用。
- **D3 agy 本輪單帳號**：`google_accounts.json` 內含帳號識別（PII），本輪不讀、不列；agy 只用 `label` 一個 alias。多帳號沿 copilot `accounts[]` 模型另開票。
- **D4 `enabled` 採「缺 key 即舊行為」**：claude／copilot account 預設 `True`、agy 預設 `False`，確保既有 config 載入後 footer 逐字元不變；以 sample yaml 快照測試釘住。
- **D5 選擇流程放在 `deploy install`，headless 為第一公民**：`--footer` 旗標是主要契約，TUI 只是「無旗標且雙向 TTY」時的便利層；無 TTY 一律 `skipped` 且 config 不動，確保 CI、乾淨 venv e2e 與 Cortex 沙箱不受影響。TUI 取消（`esc`）與 `skipped` 語意相同。
- **D6 寫回 deep-merge＋備份**：用 PyYAML `safe_load` → 只改 `enabled` 欄位 → `safe_dump` 寫回，寫前備份 `.bak-<UTC>`；接受「註解不保留」為明文限制（README 記載），不引入 ruamel 等新依賴。
- **D7 TUI 沿用 textual 0.61.1**：不新增套件；元件為 `SelectionList` + `Static` 預覽，預覽直接呼叫 `formatter` 渲染合成 snapshot，確保所見即 footer。以 `App.run_test()` Pilot 測，沿用 cockpit 測試既有模式（stub Binding 需 `**kwargs`、`set_groups` 後 Pilot 要 `pause`）。
- **D8 與 #337 的邊界**：偵測結果只服務 footer 選擇，不建 executor registry、不與 Cortex model registry 對表、不寫 `~/.agents/control`。若 #337 裁決要改讀 Cortex `doctor` 輸出，只需替換 `detect_agents()` 的資料來源，介面不變。

## Scope and verification

- 修改範圍：`paulshaclaw/cost/{config,providers,formatter}.py`、新增 `paulshaclaw/deploy/{agents,footer_select}.py`、`paulshaclaw/deploy/{__main__,installer}.py` 的旗標與 report 欄位、`paulshaclaw/config/paulshaclaw.sample.yaml`、README §Install、`changelog.d/341-footer-agent-selection.md`、新增 `tests/test_deploy_footer_selection.py` 與 `tests/test_stage8_cost*.py` 的 agy／enabled 測試。
- 不在範圍：agy 多帳號、cockpit banner 版面調整、secret 填寫互動、任何 daemon／systemd 行為、Cortex registry。
- 驗證：spec Acceptance 四條；另以 `grep -rn '/home/'` 確認新增檔無去識別化命中（R-21）。
