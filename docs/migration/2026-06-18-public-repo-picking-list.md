# 公開化搬遷 Picking List — 該搬 vs 該留 + 去識別化動作清單

> 規劃文件（planning artifact），非程式碼。對應 issue #101。
> 來源依據：`~/notes/paulshaclaw-公開評估報告-260618.md`（§1.2 污染表、§1.3 歷史陷阱、§2.2 各 stage 完成度、§5 建議路徑、附錄 A.1 去識別化難度分層、附錄 A.2 persona/coordinator 補列）。
> 字串命中數與位置由 `git grep` 於 **HEAD #108（`2fa48cc`）** 即時驗證，與本機 working tree 一致。
> 語言：zh-tw。新 repo 全新 commit 起始，本檔僅 commit 於本 repo，不 push / 不開 PR / 不 merge。

---

## 0. 路線與原則（B 路線）

- **B 路線**：策展式搬核心到「新的 clean public repo」；本 repo 去識別化無虞後 rename，維持 private 封存。
- open 價值定位是「**架構參考 / 作品集 / showcase**」，非「裝來即用的產品」→ **不要 1:1 整包搬**（#108 已 783 tracked 檔，整包搬會把信噪比與污染一起帶走）。
- 三項硬前提（見 issue #102，本檔不展開）：去識別化、LICENSE、getting-started README。本檔只負責 **搬遷範圍** 與 **去識別化動作**。

---

## 1. 該搬（核心）

策展原則：選「真的、有份量、有展示價值」的模組，且去識別化成本可控。

| 搬遷項 | 模組 / 路徑 | 量（#108 實測） | 理由 |
|---|---|---|---|
| **Stage 2 記憶 pipeline** | `paulshaclaw/memory/`（含 `memory/tests/`） | 11428 LOC / 94 檔 | 皇冠寶石、端到端天天在跑（435 slices、289 帶標題）；transcript → 原子化 → Zettelkasten → MOC → wake-up，靠地端 LLM 蒸餾，踩 agent memory 熱題。**必搬。** |
| **（選配）Stage 8 cost footer** | `paulshaclaw/cost/` + `tests/test_stage8_cost.py` | 1862 LOC | 三家 provider（Claude / Codex / Copilot）用量 footer，niche 但常被問的 pattern；含一處真 hardcode（見 §3 類 5），順手修。 |
| **精選 design / openspec docs** | `docs/research/05.*overview*`、`docs/superpowers/specs/*stage2*`、（選配）`*stage8*`、`openspec/specs/stage2-*`、（選配）`stage8-*` | — | 把「個人 agent-OS」想清楚的文字資產，有參考價值。**搬前須過去識別化**（specs 是污染重災區，見 §3）。 |
| 支援檔 | `pyproject.toml`、`requirements-*.txt`、`.github/workflows/tests.yml` | — | 讓新 repo CI 能跑測試（policy R-19 對應）。 |
| backend 範例 | `scripts/claude-gemma4`、`scripts/claude-gemma4-proxy` | — | 作為「configurable agent exec / 地端 LLM 後端」示例；**須去識別化內網 IP**（見 §3 類 6b）。 |

### 1.1 新模組決策：persona/ + coordinator/（Phases 0–4，原報告本文 #99 未涵蓋）

> 依據附錄 A.2。這兩塊是 #99→#108 期間新增，**原報告本文成文時尚不存在**，故單獨決策。

| 模組 | 路徑 | 量（#108 實測） | 是否接進 runtime | 決策 |
|---|---|---|---|---|
| persona（Phase 0–4） | `paulshaclaw/persona/`（`loader / context / contract / gate / guardrail / handoff / render / shadow / scope_ci` + `personas.yaml`） | 759 LOC（較報告 #99 的 414 LOC +83%） | **否** | **搬，但標 `experimental` / `shadow`** |
| coordinator（新模組） | `paulshaclaw/coordinator/`（`cli / registry / dispatcher / autonomy / seams` + `__main__`） | 642 LOC / 7 檔 | **否** | **搬，但標 `experimental` / `shadow`** |

**決策理由（搬 + 標 experimental，不歸「該留」也不宣稱「在跑」）**：
1. **NEW 且 self-contained**：`git grep` 確認 `paulshaclaw.persona` / `paulshaclaw.coordinator` **未被 `core` / `bot` / `cockpit` / `scripts` import**（在各自 tree 外 0 命中）。屬「有測試、有份量、但未啟用的旁路 shadow 框架」。
   - 註：`bot/listener.py` 的 `UnavailableCoordinator` 與 `cockpit/artifacts.py` 的 `coordinator_jobs_dir` 是**同名的另一抽象**（讀 JSON job 產物 / backend 介面），**非** import 新的 `coordinator/` 套件，勿混為「已 wired」。
2. **有展示價值**：persona 的 `scope-gate / shadow-gate / autonomy-gate / depends_on DAG fan-out` + coordinator dispatch 踩 agent 治理熱題（附錄 A.2 / §3.1 補充認定值得 open）。
3. **但不可宣稱在跑**：未 wired + niche + 綁個人 multi-agent infra → 僅能當「設計 + CLI 展示」搬，README 須明確標 `experimental / shadow`，**不得**寫「在跑 / 完成」（否則重蹈 §2 的灌水觀感）。
4. CI 旁證：`.github/workflows/persona-scope.yml` 為 shadow（always exit 0、非阻擋）；若搬，連同標註其為 shadow gate。

> **核心搬遷組合（附錄 A.4 修訂版）**：Stage 2 memory + （選配）Stage 8 cost + （新）persona/coordinator 治理框架（標 shadow）+ 精選 design docs。

---

## 2. 該留（封存於舊 private repo，預設不搬）

理由：死綁個人環境、library 級被動模組、或 0 LOC 空殼 — 搬了只會拉低信噪比、誤導完整度。

| 留下項 | 模組 / 路徑 | 量（#108 實測） | 理由 |
|---|---|---|---|
| Stage 1 core daemon | `paulshaclaw/core/` | 1065 LOC | 天天在跑，但死綁 daemon + bro 路由 + 個人環境。 |
| Stage 1 Telegram bot | `paulshaclaw/bot/` | 786 LOC | PaulShiaBro 主介面，死綁 Telegram / 個人 infra。 |
| Stage 1 TUI | `paulshaclaw/tui/` | **19 LOC** | 基本沒做；README 標「完成」名不副實，搬了反扣分。 |
| Stage 3 lifecycle/gate | `paulshaclaw/lifecycle/` | 445 LOC | library 級、無 CLI、被動。 |
| Stage 4 persona（legacy 定性） | — | — | **見註**：模組路徑已由 §1.1 的 Phase 0–4 取代；舊 Stage 4「11/11」定性留封存。 |
| Stage 5 觀測/health | `paulshaclaw/observability/` | 233 LOC | 偏薄 library。 |
| Stage 6 安全/ops | `paulshaclaw/security/` | 317 LOC | redaction/approval/audit，聚焦但小、被動。 |
| Stage 7 deploy | `paulshaclaw/deploy/` | 341 LOC | install/upgrade/uninstall，綁本機部署。 |
| Stage 9 project monitor | `paulshaclaw/monitor/` | 1405 LOC | 真實但綁個人工作區掃描（`~/prj_work` 等，污染源之一）。 |
| Stage 11 cockpit TUI | `paulshaclaw/cockpit/` | 933 LOC | MVP 在跑，但綁 tmux/個人 runtime；可日後選擇性搬。 |
| chat（空殼） | `paulshaclaw/chat/` | **0 LOC** | open proposal 未實作，搬了像灌水。 |
| janitor（空殼） | `paulshaclaw/janitor/` | **0 LOC** | 邏輯已併進 memory，空目錄。 |
| config（薄） | `paulshaclaw/config/` | 僅 `*.sample.yaml` + `skills.lock.yaml` | sample 本身含污染（`~/prj_work`、`org-a`），若需搬須先去識別化。 |
| 大型 / 工作區資料夾 | `ref/`、`.worktrees/`、`.venv/`、`.psc_tmp/` | — | 已 gitignore，本就不入庫；勿手動帶過去。 |

> **註（Stage 4 vs 新 persona/）**：原報告 Stage 表把 persona 列為 Stage 4「414 LOC、runtime 存疑」。#108 已是 759 LOC 的 Phase 0–4 全落地版，定位升級為「shadow 治理框架」，故**移到 §1.1「該搬（標 experimental）」處理**；此處「Stage 4(legacy)」僅指舊定性與舊測試掛載，不另搬。Stage 3/5/6/7/9/11 維持「該留」。

---

## 3. 去識別化動作表（6 類）

依報告 §1.2 污染表 + 附錄 A.1 難度分層。**判斷不變：公開即洩漏**；但工作量集中在「**test fixture 改假值** + **一處 config 重構** + **docs/specs 取代**」，真 hardcode 業務邏輯僅 1 處。

> 命中數 / 位置為 HEAD #108（`2fa48cc`）`git grep` 實測，與報告 #99 值逐項一致（附錄 A.1 已驗證「一個都沒清」）。
> 替換佔位沿用 §5/附錄：`internal-vcs.example`、`PROJECT-NNNN`、`vendor-x`、`org-a`、通用 path。

| # | 類別 | 命中字串 | 替換為 | 命中檔數 | 已知位置（代表） | 難度分層（A.1） |
|---|---|---|---|---|---|---|
| 1 | 內部 GitLab host / 公司基礎設施 | `internal-vcs.example`（連帶 `vendor-x`） | `internal-vcs.example` | 2 個 `.py` + 多 docs | `paulshaclaw/memory/tests/test_project_resolver.py:136,145,161`；`docs/superpowers/specs/2026-06-18-stage2-canary-hardening-design.md:40,41`；content-extraction specs / openspec archive | **test fixture 改假值** + **docs 取代** |
| 2 | 專案代號 | `PROJECT-0602` | `PROJECT-NNNN` | test + docs | `paulshaclaw/memory/tests/test_atomizer_prompt.py:25,29,30,39`；`test_project_resolver.py:142,148`；canary-hardening / content-extraction specs；plan `:677` | **test fixture 改假值** + **docs 取代** |
| 3 | 客戶 / 供應商名稱 | `vendor-y`、`vendor-z-mirror`（vendor-z mirror）；`vendor-x`（見註） | `vendor-x` | test + docs | `test_project_resolver.py:134,136,142,145,151,159,161`；canary-hardening design `:40,41,49,62,88` | **test fixture 改假值** + **docs 取代** |
| 4 | 內部工作區路徑 | `prj_work`、`work_prj` | 通用 path（如 `~/workspace`、`workspace/`） | 11 | `paulshaclaw/config/paulshaclaw.sample.yaml:9`；`paulshaclaw/memory/tests/test_project_resolver.py:407,416`；`openspec/changes/2026-04-26-stage9-project-monitor/*`；memory-readback specs/plans | **test fixture + sample 改假值** + **docs 取代**（Stage 9 多在該留範圍） |
| 5 | 雇主 GitHub org（含真 hardcode） | `org-a` | config 預設 / `org-a` | 12 | **真 hardcode：`paulshaclaw/cost/providers.py:807` `_COPILOT_AIU_ACCOUNT = "org-a"`（並於 `:817` 使用）**；`tests/test_stage8_cost.py`（多行）；sample.yaml:36；stage8 specs/plans | **唯一一處 config 重構**（spec 已要求 MUST NOT hardcode，亦屬真 bug）+ fixture 改假值 + docs 取代 |
| 6a | 個人 PII（低） | `you@example.com` | 移除 / 佔位 | 2 | `docs/research/04.stage4-persona-...md:935`；`docs/research/05.paulshaclaw-overview-...md:8` | **docs 取代**（04 屬該留；05 在搬遷清單，須清） |
| 6b | 內網 IP（低） | `192.0.2.10`（:8001 / :8000） | config 預設 / `llm-host.example` | 15 | **runtime 預設：`paulshaclaw/memory/importer/title.py:40`、`scripts/claude-gemma4-proxy:9`（皆已 env 可覆寫，僅改 default 佔位即可，非 config 重構）**；`scripts/claude-gemma4:141`（描述字串）；`paulshaclaw/memory/tests/test_title.py:117`（fixture）；chat-api / phase2 specs | **改 default 佔位** + fixture 改假值 + docs 取代 |

**難度總結（A.1）**：
- **真 hardcode 業務邏輯：僅 §類 5 的 `providers.py:807` 一處** → 需 config 重構。
- §類 6b 的兩個 runtime 點（`title.py:40` / `claude-gemma4-proxy:9`）**已支援 `PSC_CLAUDE_GEMMA4_UPSTREAM_URL` 覆寫**，去識別化只需把「default 字面值」換成佔位，**不算 config 重構**。
- 其餘 `.py` 命中幾乎全是 **test fixture**（`test_project_resolver.py` / `test_atomizer_prompt.py` / `test_stage8_cost.py` / `test_title.py`）→ 改假值即可，改完須保持測試綠。
- 大量命中散在 **docs / specs / openspec**（含 archive）→ 文字取代；其中屬「該留」範圍的（Stage 9 monitor、research 04、chat-api、legacy plans）**根本不搬**，等同自然消除。

> **註（vendor-x）**：`vendor-x` 唯一命中在 `docs/superpowers/specs/2026-04-21-hamanpaul-project-policy-design.md:7`，語境是「policy 適用範圍排除工作專案（含 Vendor-X 等）」，屬政策文件用語、非交付目標洩漏；該 policy design 不在搬遷清單，可不單獨處理。報告 §1.2 將 vendor-x 與 vendor-y/vendor-z 並列為供應商名，搬遷時若涉及該檔仍按 `vendor-x` 取代。

### 3.1 0-命中驗證 grep

搬遷後新 repo 應對下列字串全數 **0 命中**：

```bash
git grep -nE "vendor-x|org-a|PROJECT-[0-9]|\bvendor-y\b|vendor-z-mirror|prj_work|work_prj|192\.0\.2\.10|you@example\.com"
```

（若刻意保留某佔位範例字串，須確認其為假值如 `internal-vcs.example` / `org-a` / `PROJECT-NNNN`，且不在上列 pattern 內。）

---

## 4. 歷史陷阱 + 全新 commit 起始 note

> 依據報告 §1.3 與 §5.5。

- **陷阱**：GitHub repo 由 private 切 public 會**連整段 commit 歷史一起公開**。即使現在 `git rm` / 改字串，舊 commit（含 §3 的所有污染字串）仍可被瀏覽。
- **本路線（B）做法**：新 repo **以全新 commit 起始（不帶舊歷史）**，自動規避歷史公開陷阱。
  - **勿** `git push` / `git filter-repo` 把舊 repo 歷史原樣推過去。
  - 搬遷方式：複製「已去識別化」的檔案內容到新 repo 後，於新 repo 做 **初始 commit**（乾淨起點）。
  - 舊 repo 去識別化無虞後 **rename 封存、維持 private**（不轉公開，故其歷史不外洩）。
- 對照 A 路線（不採）：原 repo 去識別化 + `git filter-repo` 重寫歷史會改 SHA、force-push、破壞既有 PR/issue 連結，且歷史仍難保證全淨；B 路線歷史最乾淨。

---

## 5. 完成定義（DoD）

- [ ] 核心模組（Stage 2 memory +（選配）Stage 8 cost + 精選 design/openspec docs + persona/coordinator 標 experimental）搬入新 repo
- [ ] 新 repo CI（`tests.yml`）跑 `pytest` 全綠（對應 policy R-19；基準 #108 = 1198 passed / 1 skipped）
- [ ] §3 六類去識別化逐項替換完成（fixture 改假值、`providers.py:807` config 重構、docs/specs 取代）
- [ ] §3.1 的 0-命中驗證 grep 在新 repo **0 命中**
- [ ] 空殼（chat/janitor/tui）與環境綁定模組（core/bot/Stage 3/5/6/7/9/11）已排除；未排除者明確標 `experimental`
- [ ] persona/coordinator 在 README 標 `experimental / shadow`，**未**宣稱「在跑 / 完成」
- [ ] 新 repo 以全新初始 commit 起始（不帶舊歷史）；舊 repo rename + 維持 private 封存
- [ ] README + LICENSE 兩項硬前提另由 #102 交付（本檔不含）

---

*本 picking list 基於 2026-06-18 HEAD #108（`2fa48cc`）`git grep` 實測；字串命中數與報告 §1.2 / 附錄 A.1 逐項一致。相關：#102（新 repo README + LICENSE 骨架）。*
