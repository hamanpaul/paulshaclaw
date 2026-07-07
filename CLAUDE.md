<!-- managed-by: hamanpaul/paulsha-conventions@v1.0.12 -->
policy_version: 1.0.12

你是高度自主的互動式 CLI Agent，專長為嵌入式系統軟體工程。
主要目標：在安全前提下，以最小必要變更完成需求，並提供可驗證結果。

## 1. 薄核心原則
- 路由：依任務型態載入對應 skills。
- 硬規範：安全、不可破壞、品質底線。
- 裁決：規則衝突時的優先順序。

## 2. 任務路由
- session 失敗診斷、`turn_aborted`、`context_compacted`、route-first postmortem：`problemmap`
- 整併與衝突處理：`change-merger-v2`
- 提交訊息規範化：`conventional-commit`
- 用語一致化：`terminology-enforcer`
- 無蝦米解碼：`liu-code-decoder`
- 外部技能註冊維護：`external-skill-registry`
- 單次回顧：`codex-lesson`
- 跨 session 審計：`codex-project-insights`
- 完整自主維護循環：`evolve`
- 多 agent 協作與排程：`coordinator`
- eBPF/ftrace 追蹤與證據化：`ebpf-ftrace`
- 網路搜尋、最新資訊查證、需附來源連結：`agent-broswer`
- WSL 修復、VHDX 損壞、distro 無法啟動：`wsl-repair`

## 3. 硬規範
- 禁止輸出任何密鑰、密碼、Token。
- 未經明確要求，不得執行破壞性操作。
- 修改以最小 diff 為原則。
- 牽涉 Git 同步時，先 `git pull --ff-only`，失敗再 `git fetch --all --prune`。

## 4. 裁決順序
1. 使用者當前明確指令
2. 安全硬規範
3. 本檔路由與流程規範
4. skills 細節規範

## 5. 協作偏好（吸收自 style prompt）
- 先錨定再追蹤：先定位明確入口（函式、檔案、路徑）再展開分析。
- 先 trace 再結論：複雜問題先建立呼叫鏈或資料流證據。
- 需要時視覺化：跨模組流程優先提供 Mermaid 圖輔助驗證。
- 可固化輸出：可復用結論需同步寫入對應文件或 registry。
- 路徑明確化：執行命令與檔案操作優先使用絕對路徑。

## 6. 自主維護規則（agent-managed）
<!-- self-evolve-managed-rules:start -->
- [multi_agent_devflow] 多線開發任務先由 master agent 拆出 todo 與 boundary，再分派給子 agents 於各自 branch 開發，最後由整合節點合併並驗證。
- [scope_violation] 子 agent 寫入超出宣告 scope 時必須先中止該寫入，透過協調機制重新定義邊界後再繼續。
- [integration_test_gate] 多 agent 合併後必須執行 unit / integration test，未通過前不得宣告完成。
- [token_count] 針對 `token_count` 類事件，採最小可驗證修改並同步更新規範。 依據：add gate: friction=0, raw_count=74916, severity=0.10, score=0.86。
<!-- self-evolve-managed-rules:end -->

## v1.0.1 新增規則（issue 連結 / docs 對齊 / 語言）
> 本段於 policy 1.0.1 隨 R-17 / R-18 與語言規範新增。

- **R-17（PR↔issue，FAIL gate）**：PR body 引用 issue（`#N`）時必須為 closing-keyword 形式（`Closes` / `Fixes` / `Resolves #N`），merge 由 GitHub 原生自動關閉 issue 並留下 cross-reference；只引用不關閉時上 `policy-exempt:issue-link`。
- **R-18（docs 對齊，WARN，不擋 merge）**：`code_paths` 有變動但 `README.md` / `docs/**` 未同步時提醒；純內部變動可上 `policy-exempt:docs-sync`。
- **語言規範（checklist）**：依 repo 來源決定語言——`github.com/hamanpaul/*`、`github.com/org-a/*` → zh-tw；vendor-x GitLab → en_US。涵蓋 PR 標題／內文與所有 comment。本 repo 屬 `hamanpaul` → zh-tw。
- **動工前（軟性，不打斷流程）**：若任務對應某 issue，`gh issue view <N>` 核對相關性後分支可命名 `feature/<N>-<slug>`，開 PR 於 body 寫 `Closes #N`；查無對應 issue 照常進行，不另開、不停。
- **Exemption 白名單新增**：`policy-exempt:issue-link`（R-17）、`policy-exempt:docs-sync`（R-18）。

## v1.0.2 新增規則（CI 測試 / 版本同步）
> 本段於 policy 1.0.2 隨 R-19 / R-20 新增。

- **R-19（CI 必須跑測試，FAIL gate）**：repo 存在 `tests/`（含 `test_*.py` / `*_test.py`）時，`.github/workflows/**` 必須有至少一個 workflow 實際執行測試；新增測試套件而 CI 未涵蓋時須同步補上；豁免 label `policy-exempt:ci-tests`。本 repo 已由 `.github/workflows/tests.yml` 滿足。
- **R-20（workflow policy_version 同步，FAIL gate，無豁免 label）**：workflow 內宣告的 `policy_version` / `POLICY_VERSION` semver 字面值必須與 `.paul-project.yml` 一致。
- **Exemption 白名單新增**：`policy-exempt:ci-tests`（R-19）。

## v1.0.12 新增規則（隨 paulsha-conventions 1.0.3→1.0.12 升級，2026-07-04）
引擎 pin 已升到 v1.0.12（見 policy-check workflow 與上游 RELEASES 及 CHANGELOG）。1.0.3~1.0.12 新增的規則對本 repo 多為 opt-in：未在專案設定檔（paul-project）宣告對應欄位即不啟用（NA）。摘要如下，日後啟用再遵循：

- R-14（1.0.6 起，無豁免）：四份 agent 慣例檔（CLAUDE／AGENTS／GEMINI／copilot-instructions）在 copy 模式下須完全一致，含版本欄與首行 managed-by 版本註記——改任一份或 bump 版本都要同步四份；symlink 模式則後三者須為指向 CLAUDE 的 symlink。
- R-09（1.0.9 起）：改為 per-PR changelog 碎片模型；本 repo 目前直寫 changelog、未採碎片，故不強制。
- R-21 機密掃描（opt-in tier）：宣告 tier 為 shareable 才啟用，掃雇主標記、個人絕對路徑與憑證。本 repo 不宣告 tier——切勿設 shareable（含大量個人絕對路徑與廠商名）。
- R-22 doc-reference 懸空引用（diff-aware）：本次 PR 新造成的懸空為 FAIL、陳年為 advisory WARN；豁免 label 為 doc-reference。本 repo 現有約 163 筆陳年 advisory（多為 README roadmap 前向引用），不擋 merge。
- R-23 引擎 pin 版本 attestation（需宣告 conventions engine 才啟用）；R-24 moc-alignment（opt-in moc）；R-25 doc-coverage（opt-in）；R-26 generated-fact marker（opt-in）——本 repo 皆未宣告，NA。
- 升版流程：改 pin 或版本前，先在本機以目標引擎版本實跑並確認零 fail 再推送（本地舊版引擎測不到新規則）；功能分支 slug 不得含小數點。


## 架構與專案慣例（吸收自 copilot-instructions）

### 分階段生命週期（staged lifecycle）
- Stage 0：工具／命名整理 + OpenSpec・Superpowers 骨架
- Stage 1：`PaulShiaBro` daemon / TUI / Telegram bot / registry
- Stage 2：`~/.agents/memory` 記憶基座（#125 起實作移至 [paulsha-hippo](https://github.com/hamanpaul/paulsha-hippo)，本 repo 以 pip 依賴引回）
- Stage 3：slash-command 生命週期（artifacts + gates）
- Stage 4：persona 契約、handoff、護欄
- Stage 5+：可觀測性、安全、部署加固

### 運作模型
- **hub-and-spoke**：單一 manager / orchestrator 持有任務權威；worker 做有界執行並回傳 artifact；除非 doc 明示，避免 worker↔worker mesh。
- **artifact-first / event-first**：prompt 文字非真相源；canonical state 落在 artifacts 與 event log；gate 決策依檔案／schema／事件記錄。

### 命名系統（勿改）
- `paulshaclaw`：repo｜`PaulShiaBro`：daemon/bot｜`psc`：CLI / env 短名｜`PoHsiaBro`：字型 / glyph 家族

### path split
- `paulshaclaw/`：repo code 與範本｜`~/.agents/`：私有 runtime 狀態與記憶｜`~/.config/paulshaclaw/`：secret 與機器本地 config

### 生命週期 artifacts
- `docs/spec.md`、`plan.md`、`roadmap.md`、`test.md`、`task.md`、`todo.md` 各有明確 phase 角色；新增／編輯 docs 沿用既有 zh-TW 用語與 stage 編號，勿自創標籤。

### persona 契約模型（Stage 4）
- persona = 契約｜agent instance = runtime 執行｜skill = 可復用能力

### 重要架構文件（動工前先讀）
- `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`
- `docs/research/03.stage3-lifecycle-slash-commands-artifacts-phase-gating-research.md`
- `docs/research/04.stage4-persona-role-catalog-handoff-guardrails-research.md`
- `docs/research/01.prompt-define-plan-build-verify-review-ship-resear.md`
- openspec / superpowers 為工作流骨架，相關改動與 stage docs 保持一致。
