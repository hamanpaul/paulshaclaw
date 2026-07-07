## 1. Cortex repo 建立（外部前置，於 paulsha-cortex repo 內執行）——✅ 完成 2026-07-07（PR #1 merged）

- [x] 1.1 Phase 0 骨架：new-project-template 起 repo（無歷史）、pyproject（package `paulsha_cortex`）、tests CI（R-19）、policy engine pin v1.0.12、tag ruleset、R-21 shareable tier
- [x] 1.2 Phase 1 平移：`persona/**`、`coordinator/**`、`control/**` 三包與約 25 個測試檔遷入
- [x] 1.3 剪線一：PHASES 7 字串常數自帶（persona contract 改讀本地常數，移除 `paulsha_hippo.lib.lifecycle` import）
- [x] 1.4 剪線二：`lib/idle.py` 23 行 vendor 進 cortex（含來源 hippo commit 註記）
- [x] 1.5 剪線三：cortex 自帶 paths 模組（`control_root`/`coordinator_root`/`repo_root`/`specs_root`/`worktree_root`，遵守 `PSC_*` env 覆寫契約；repo_root 改 `PSC_REPO_ROOT`→cwd）
- [x] 1.6 cortex console script 與 `install service`（manager systemd 單元出貨、冪等實作）
- [x] 1.7 relay-hook/notifier/hooks json 平移（`dispatch-stage-wave-a.sh`/`copilot-stage-worker.sh` 留主 repo）；`service-manager.sh` 參數化；persona-scope CI workflow 於 cortex 續跑
- [x] 1.8 cortex 全測試綠（277 passed）；單寫者 flock（`manager.lock`）測試隨包平移確認
- [x] 1.9 產出 pin 用 commit SHA：**`2e67100d1184bcaa26bce313f84c388e86f35928`**（Plan 2 主 repo 遷移刀以此 pin）

> **codex 對抗審查（兩輪）已解**：R1 F2/F3/F4（PY 解譯器 persist、`--repo-root`+PSC_REPO_ROOT、`cortex relay-hook` + 剝 bro-return glue）、R2（env 只更新 managed keys、execv 對 0644 bash fallback）。F1（`stop_legacy_manager_timer` 自停）為 paulshaclaw verbatim 繼承、非拆分回歸 → cortex issue #2 follow-up。fresh-install 0644 fallback 實測通過。

## 2. 主 repo 遷移刀

- [ ] 2.1 pyproject 新增 `paulsha-cortex @ git+https://...@<sha>` pin
- [ ] 2.2 刪除 `paulshaclaw/{persona,coordinator,control}/**`
- [ ] 2.3 `bot/listener.py`、`cockpit/app.py`、`core/daemon.py` import 改 `paulsha_cortex.control.client`
- [ ] 2.4 `psc coordinator` thin shim：lazy import cortex CLI、未安裝時 tombstone 文案 + exit 2
- [ ] 2.5 `deploy/planner.py` 移除 manager 單元模板引用；刪除 `__INSTANCE__-manager.{service,timer}.tmpl`
- [ ] 2.6 移除 `scripts/coordinator/**`、`scripts/service-manager.sh`、`.github/workflows/persona-scope.yml`
- [ ] 2.7 遷出測試檔移除；W7 整合測試改 import cortex
- [ ] 2.8 grep 清零：`paulshaclaw.persona|paulshaclaw.coordinator|paulshaclaw.control` 無殘留（shim 除外）；import 面 CI 檢查落地（cortex 允許清單 + hippo runtime import 清零、tests 僅限對齊測試）

## 3. 對齊測試（主 repo 為契約交會點）

- [ ] 3.1 PHASES 相等性測試：cortex 自帶常數 == `paulsha_hippo.lib.lifecycle.schema.PHASES`
- [ ] 3.2 paths 等價測試：cortex paths 模組與 `config.paths` facade 於相同 env 覆寫組合下五個 root 全等
- [ ] 3.3 `test_deck_contract_alignment` 改線：deck `persona_binding` 對照 cortex personas.yaml
- [ ] 3.4 cortex 零 hippo 依賴斷言（依賴解析集合不含 paulsha-hippo）

## 4. 文件與 spec 遷移

- [ ] 4.1 CLAUDE.md／README 治理平面章節改指向 cortex；命名系統新增 `paulsha-cortex`（R-18 同 PR）
- [ ] 4.2 openspec/specs 遷移：`coordinator-cli`、`coordinator-tick`、`coordinator-completion-tick`、`coordinator-headless-dispatch`、`manager-control-plane`、`persona-skills-binding`、`stage4`（persona 部分）遷入 cortex openspec

## 5. Phase 3 驗收（E2E + cutover）

- [ ] 5.1 fresh-install E2E：乾淨環境 `pip install paulsha-cortex` 單獨可用、不拉 hippo
- [ ] 5.2 systemd cutover 實走：stop+disable 舊 manager 單元 → enable cortex 單元 → complete tick 通過
- [ ] 5.3 `install service` 冪等重跑驗證
- [ ] 5.4 雙 daemon 鎖競爭驗證：舊 daemon 未停時啟動 cortex daemon，第二實例因 `manager.lock` 退出
- [ ] 5.5 rollback 演練：revert 主 repo pin + 重 enable 舊單元
- [ ] 5.6 主 repo 全測試綠（worktree 假失敗以無變更 worktree 交叉驗證）
