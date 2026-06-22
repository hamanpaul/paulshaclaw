> 詳細逐步程式碼見 `docs/superpowers/plans/2026-06-22-persona-manager-phase-a.md`。每組依 TDD（RED→GREEN→commit）。

## 1. 前置

- [ ] 1.1 `git pull --ff-only`（失敗則 `git fetch --all --prune`）後 `git switch -c feature/persona-manager-phase-a`（勿在 main 實作）

## 2. enforcement 旗標（stage4）

- [ ] 2.1 `personas.yaml` 加頂層 `enforcement: shadow`
- [ ] 2.2 寫 `tests/test_persona_enforcement_flag.py`（預設 shadow／enforce 讀出／缺 key・非法・缺檔・壞 YAML 退 shadow），跑出 RED（`ImportError: load_enforcement`）
- [ ] 2.3 在 `loader.py` 實作 `load_enforcement(path=None)`（fail-safe 退 shadow），跑出 GREEN
- [ ] 2.4 跑 `tests/test_persona_config_loader.py` 確認既有 loader 測試不回歸
- [ ] 2.5 commit（conventional，含 Co-Authored-By）

## 3. build_dispatch_command（coordinator-cli，強制點 ①）

- [ ] 3.1 寫 `tests/test_coordinator_contract_command.py`（含契約/task/plan、shlex 單 token、未知 role raise、純函式零 I/O），跑出 RED（`ModuleNotFoundError`）
- [ ] 3.2 建 `paulshaclaw/coordinator/contract_command.py`：`DEFAULT_EXECUTOR` + `build_dispatch_command`（reuse `render.render_contract_prompt`、`shlex.join`），跑出 GREEN
- [ ] 3.3 commit（conventional，含 Co-Authored-By）

## 4. dispatch_ready 接線（coordinator-cli）

- [ ] 4.1 在 `tests/test_persona_phase4_fanout_autonomy.py` 加 `test_dispatch_ready_command_carries_persona_contract`，跑出 RED（佔位字串斷言失敗）
- [ ] 4.2 `autonomy.py` 頂部 import `build_dispatch_command`，`dispatch_ready` 的 `command=` 改用之（取代佔位註解），跑出 GREEN
- [ ] 4.3 跑整個 `tests/test_persona_phase4_fanout_autonomy.py` 確認不回歸
- [ ] 4.4 commit（conventional，含 Co-Authored-By）

## 5. 驗收閘門

- [ ] 5.1 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 全綠（與 CI 同綠、零行為回歸）
- [ ] 5.2 確認零 live 接觸（未碰 daemon／systemd／tmux／真 copilot）
