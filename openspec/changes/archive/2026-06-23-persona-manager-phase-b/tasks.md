> 詳細逐步程式碼見 `docs/superpowers/plans/2026-06-22-persona-manager-phase-b.md`。每組依 TDD（RED→GREEN→commit）。本 change 疊在 `feature/persona-manager-phase-a` 上。

## 1. 前置

- [ ] 1.1 自 `feature/persona-manager-phase-a` 開 `feature/persona-manager-phase-b`（疊放，A 未 merge）

## 2. prompt 重構（coordinator-cli）

- [ ] 2.1 RED：`build_dispatch_prompt` 測試（契約段+task+plan ref、無 shell 字樣、未知 role raise、零 I/O）
- [ ] 2.2 GREEN：`contract_command.py` 由 `build_dispatch_command`（shlex shell 字串）重構為 `build_dispatch_prompt`（純文字）
- [ ] 2.3 commit

## 3. AgentLauncher seam + 三 executor（coordinator-headless-dispatch）

- [ ] 3.1 RED：`AgentLauncher` Protocol + 三 executor argv 組裝測試（copilot/claude/codex 各自旗標、prompt 單一 arg、cwd、env PSC_SLICE_ID）
- [ ] 3.2 GREEN：`launcher.py` 三真實作（headless + remote + JSONL + autonomous + cwd），seam 可注入 fake
- [ ] 3.3 commit

## 4. registry 擴充 + 完成偵測

- [ ] 4.1 RED：registry 記 executor/session_name/pid/log_path/exit_code round-trip；完成偵測（exit+JSONL done/failed、壞 JSONL fallback）
- [ ] 4.2 GREEN：擴 `registry.py` 欄位 + 完成偵測函式
- [ ] 4.3 commit

## 5. 進度 relay hook（三家共有 session_start/stop）

- [ ] 5.1 RED：relay hook script 對 fake env+event 產正確 payload；relay 失敗不拋
- [ ] 5.2 GREEN：`scripts/coordinator/psc-relay-hook.sh` + 三家 hook 註冊範本；接 bro-bridge
- [ ] 5.3 commit

## 6. dispatch_ready 接 headless

- [ ] 6.1 RED：`dispatch_ready` 以 fake AgentLauncher 驗就緒單位 → launch 呼叫（取代佔位/pane send）
- [ ] 6.2 GREEN：`autonomy.py` 改用 `build_dispatch_prompt` + 注入的 `AgentLauncher.launch`
- [ ] 6.3 commit

## 7. smoke test 待驗（不擋單元測試）

- [ ] 7.1 各跑一次真 executor headless，確認 hook 是否 fire、autonomous/remote 旗標、session id 取得；結果記入 design spec §6/§10
- [ ] 7.2 不 fire hook 的 executor 退 JSONL 監控 relay

## 8. 驗收閘門

- [ ] 8.1 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 全綠（零行為回歸）
- [ ] 8.2 確認路徑 1（route_to_agent）未被動到
