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

## 1b. deck + monitor 進 cortex（R1 採 B 新增，於 paulsha-cortex repo 內，另出 Plan 1b）

- [ ] 1b.1 平移 `deck/**`（835 行）+ `monitor/**`（1412 行）+ 各自測試進 cortex；import 改 `paulsha_cortex.*`（兩者僅 import `config.paths`，cortex 已自帶 → 零新剪線）
- [ ] 1b.2 CLI：`cortex deck …`、`cortex monitor …` 子命令接線；`cortex` 傘狀入口路由
- [ ] 1b.3 persona↔deck：既有 fail-open lazy import 可改為正常 import（同包後不再需要 fail-open）；或保留亦可
- [ ] 1b.4 monitor merge adapter（R1.6）：讀 `project-cortex.yaml`（手寫）⊍ `project-hippo.yaml`（缺則 graceful 退 manual-only）、依路徑/身分去重；config 由 `paulshaclaw.yaml` 改名 `project-cortex.yaml`、base dir 統一（相容過渡讀舊路徑）
- [ ] 1b.5 monitor 服務併入 `cortex install service`（一次裝 manager + monitor 兩 unit，不拆；monitor single-instance 沿用 socket 佔用檢查）
- [ ] 1b.6 persona 重定義（R1.7）：實查無 code 把 contract 與 enforcement 混在一起，docs/命名澄清（AgentInstance/Persona/Guardrail/Manager）
- [ ] 1b.7 去識別化 + 零依賴（deck/monitor 不引入新依賴；讀 `project-hippo.yaml` 為檔案契約非 import hippo）；cortex 全測試綠
- [ ] 1b.8 #186 deck Phase B/C 續作入口隨 deck 移入 cortex repo（openspec/issue 轉址）
- [ ] 1b.9 產出新 pin SHA（Plan 2 以此 pin，取代 §1 的 `2e67100`）

> **閉環（R1.9）非 Plan 1b 範圍**：deck+monitor 只搬入、擺放不擋 feedback edge 接點；monitor→manager 觸發（含情境1 去重）、失敗 retry（情境2）、hold→auto 自動化（情境3/G2）皆為拆分後 feature。

## 2. 主 repo 遷移刀（R1：刪 5 包）

- [ ] 2.1 pyproject 新增 `paulsha-cortex @ git+https://...@<1b 新 sha>` pin
- [ ] 2.2 刪除 `paulshaclaw/{persona,coordinator,control,deck,monitor}/**`
- [ ] 2.3 主 repo 消費者 import 改線：`control.client`（bot/listener、cockpit/app、core/daemon，含**相對 import** `from ..control`）、deck 消費者（cli.py、persona—已隨包移出）、monitor 消費者（cockpit 若 python import；否則 HTTP/檔案不動）→ 改 `paulsha_cortex.*`
- [ ] 2.4 `psc coordinator|deck|monitor` thin shim：lazy import cortex CLI、未安裝時 tombstone + exit 2
- [ ] 2.5 `deploy/planner.py` 移除 manager 單元模板引用；刪除 `__INSTANCE__-manager.{service,timer}.tmpl`
- [ ] 2.6 移除 `scripts/coordinator/**`、`scripts/service-manager.sh`、`.github/workflows/persona-scope.yml`、deck/monitor 相關 workflow
- [ ] 2.7 遷出測試檔移除；W7 整合測試改 import cortex
- [ ] 2.8 grep 清零：`paulshaclaw.{persona,coordinator,control,deck,monitor}`（含相對 import 形式）無殘留（shim 除外）；import 面 CI 檢查落地

## 3. 對齊測試（主 repo 為契約交會點）

- [ ] 3.1 PHASES 相等性測試：cortex 自帶常數 == `paulsha_hippo.lib.lifecycle.schema.PHASES`
- [ ] 3.2 paths 等價測試：cortex paths 模組與 `config.paths` facade 於相同 env 覆寫組合下五個 root 全等
- [ ] 3.3 deck↔persona 對齊：`persona_binding` 對照 cortex personas.yaml（deck 已在 cortex 內 → 改為 cortex 內部測試 + 主 repo 消費面 smoke）
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
