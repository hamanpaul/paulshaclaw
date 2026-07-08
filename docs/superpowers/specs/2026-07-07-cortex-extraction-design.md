# paulsha-cortex 拆分設計（治理包 persona + coordinator + control 外部化）

> 真相源：本檔為 #125 Phase 2（治理包）拆分的架構設計。裁決過程見 2026-07-07 session（brainstorming 流程）。
> 相關：#125（切包 umbrella，Phase 2 定義處）、#186 §6（deck 歸屬三分裁決）、#124（G2 enforce 翻牌，本次非目標）、`2026-07-06-memory-extraction-hippo-design.md`（Phase 1 刀法先例）。

## ⚠️ 修訂 R1（2026-07-07，採 #233「走 B」+ brainstorm 收斂）

> 本 §R1 覆寫下方 §1–§9 受影響決策。§1–§9 保留為 R1 前（形式 A）原文與裁決軌跡；衝突處以 R1 為準。

### R1.1 定位與範圍
cortex 從「治理 runtime」升級為**完整 task-management plane**：`coordinator + control + persona + deck + monitor`，走 `define → dispatch → govern → observe` 迴圈。

### R1.2 組裝模型
```
   完整 paulshaclaw 部署 = operator shell（主 repo）+ hippo + cortex
   operator shell：cockpit · bot · cost · deploy glue · 跨包對齊測試
        │ pip dep（SHA pin）          │ pip dep（SHA pin）
        ▼                             ▼
     hippo（記憶）                cortex（任務管理）
   三者各自可獨立 pip 安裝運作，靠穩定契約組合，不互 import internals。
```

### R1.3 scope 變更（推翻 §2「deck 留主 repo」、§7 非目標「deck 搬移」）
`deck/`（835 行，任務定義／combo 編譯）+ `monitor/`（1412 行，任務狀態快照）**納入 cortex**。
裁決 lens（standalone user）：一般 user 要走完整迴圈，形式 A 連「定義任務」都得跳回主 repo 的 deck，完不成迴圈；deck 是非作者 user 的建立任務前門（核心）、monitor 是觀察 companion。依賴實測：deck/monitor 各只 import `config.paths`（cortex 已自帶）、coordinator 不 import 兩者、彼此檔案/HTTP 解耦 → 零新耦合、**A′ 零依賴不變**。

### R1.4 process 編排（裁決）
各元件**自帶 install service**，operator shell 只協調（enable/start/status，不背景拉 process）。**`cortex install service` 一次裝 manager + monitor 兩個 unit（不拆）**。消除 F1「背景拉 vs systemd」dual-model 張力。

### R1.5 inter-component 契約
- **state = 檔案**（artifact-first，`~/.agents/*`）——最解耦的跨語言契約，無需 server 常駐
- **live-query = Unix socket**（monitor；跨語言/遠端需求才升 localhost HTTP）
- **definition ops = CLI**（`cortex deck compile` 等純函式，不需 server）
- **不鋪 REST-mesh**——會重新引入 runtime 耦合、違背 hub-and-spoke

### R1.6 project registry（monitor 監控集 = 兩份 merge）
monitor 監控集 = `project-cortex.yaml`（手寫，由 `paulshaclaw.yaml` 改名，curated intent）**⊍** `project-hippo.yaml`（hippo 產生，discovered activity）。檔案契約（cortex 讀共享檔非 import hippo，零依賴不破）。**契約下列各項為 Plan 1b 硬需求，非留白**（對抗審查 finding 2）：

- **canonical base dir**：`~/.agents/config/paulsha/`（兩份 merge-source 共置；project registry 屬 runtime 共享狀態，歸 agents config root）。→ `~/.agents/config/paulsha/project-cortex.yaml`、`~/.agents/config/paulsha/project-hippo.yaml`。新增 `paths.project_config_root()`，env 覆寫 `PSC_PROJECT_CONFIG_ROOT`。
- **manual 讀取順序（含 legacy 過渡）**：`PSC_MONITOR_CONFIG`（顯式）> `PAULSHACLAW_CONFIG`（既有 env，deprecated 警告）> `~/.agents/config/paulsha/project-cortex.yaml` > `~/.config/paulshaclaw/paulshaclaw.yaml`（legacy，deprecated 警告）。命中第一個存在者為 manual 來源。
- **merge 語意**：union；**dedupe key = 解析後絕對路徑（realpath）**；同 path 出現於兩份 → 算一個 project、manual 的顯式欄位（name 等）優先。
- **缺檔行為**：`project-hippo.yaml` 缺 → graceful 退 manual-only；manual（含 legacy）全缺但 hippo 在 → hippo-only；**兩來源皆缺 → FAIL 並印明確訊息**（monitor 無對象可監控，不得靜默空跑）。
- monitor 側：加 merge adapter（把 workspaces walk 與明確 roots 歸一成 project 路徑集）——Plan 1b scope，驗收情境見 openspec `cortex-consumer`。
- hippo 側：hippo 從既有 `resolve_project`（git toplevel/remote）持久化 mapping 寫 `project-hippo.yaml`——**paulsha-hippo#14（deferred，含 auto-append／保留手改／opt-in）**，與 cortex 拆分分軌。

### R1.7 persona 重定義（#233 §2）
persona = manager 與 guardrail 共同引用的**角色契約資料**（role profile + scope subject）；**不是**執行者（AgentInstance = runtime session）、**不是**安全管理者（guardrail／policy engine 讀契約做 enforcement）。code 已分離 `PersonaContract`／`PersonaGuardrail` → 多為 docs/命名澄清（**Plan 1b 實查確認無 code 把 contract 與 enforcement 混在一起**）。

### R1.8 deck↔coordinator
同包後「deck 產 spec、`coordinator.autonomy` 解析」的契約變 **intra-cortex**；原 Plan 2 跨包對齊測試簡化為 cortex 內部測試 + 主 repo 消費面 smoke。

### R1.9 閉環分析（cortex roadmap 錨點：拆分只搬器官、不閉環）
**兩層迴圈**：
- **① 組合內**（單 combo 的 stage 推進）——**現已閉合**：deck 編出帶 `depends_on` 的 slice specs DAG → manager 依 dep 序派 stage → 完成偵測 → 下一 stage（不需 monitor）。
- **② 新工作進場**——需 feedback edge（新建）：`monitor 偵測新 plan → (deck compile) → specs 佇列 → manager poll`。artifact-first：monitor 不直接命令 manager，丟進佇列由 manager 自 poll（守 hub-and-spoke）。

**閉環要「閉得對」的 3 個已知邊界**：
| # | 情境 | 處置 |
|---|---|---|
| 1 | **feedback 震盪**：agent 執行改 project 檔案 → monitor 誤觸發正在執行的工作 → 重複派工/無限迴圈 | **feedback 設計必含去重**：enqueue 前對 specs 佇列 + job registry 檢查（已在佇列/已是 job/已完成 → 不重觸發）。artifact-first check-before-enqueue |
| 2 | **失敗無回授分支**：agent 做爛/逾時無自動 retry/escalate/park，task 卡住 | 拆分後新 feature（新 retry 能力） |
| 3 | **hold→auto 安全閘 = 半自主**：spec 預設 `dispatch:hold`，翻 auto 需人/政策 | 是安全設計非 bug；全自動化 = G2/#124 enforcement + policy |

**閉環各缺口的家**：①feedback+選牌 = deck Phase B/C（#186）+ #23；②enforcement = G2/#124；③observe 接線 + retry = 新 cortex feature。**Plan 1b/2/3（拆分）只搬器官、不接這些線**，只要 monitor/manager/deck 擺放不擋到接點。

### R1.10 CLI 終態
`cortex coordinator|deck|monitor|install|relay-hook`（各自可獨立用、組成迴圈）；主 repo `psc deck|coordinator|monitor` → thin shim。

### R1.11 修訂後 plan 鏈
Plan 1 ✅（persona+coordinator+control merged，pin `2e67100`）→ **Plan 1b**（deck+monitor 進 cortex：平移 + `cortex deck|monitor` CLI + monitor merge adapter + config 改名 `project-cortex.yaml` + monitor 併入 `install service` + persona docs 澄清）→ Plan 2（主 repo 刪 **5** 包、pin 新 SHA、import 改線含相對 import、shim、對齊測試）→ Plan 3（E2E + systemd cutover）。**#186 deck Phase B/C 隨 deck 移入 cortex repo**。

## 1. 目標與定位

把治理平面（manager 派工決策 + persona scope 護欄 + control 檔案契約控制面）拆為獨立 repo **paulsha-cortex**（package 名 `paulsha_cortex`），命名延續 paulsha-hippo 的腦區隱喻（前額葉皮質 = 執行功能 + 行為抑制）。

核心要求：**cortex 可單獨 pip 安裝，對 paulsha-hippo 零依賴**——persona 的跨 vendor 定位不被記憶產品綁架。

## 2. 決策記錄（2026-07-07 session 已裁決）

| 決策 | 裁決 | 理由 |
|---|---|---|
| 一支 repo vs 兩支 | **一支**（persona + coordinator + control 同包） | 三模組合計約 3.3k 行（hippo 拆出時 31k），拆兩支開銷 ×2；G2 enforce 將同時動 manager dispatch 與 persona gate，同 repo 才有 atomic PR；#125 Phase 2 本就把三者定義為同一治理包；manager→persona 單向依賴留在 repo 內部，未來真有獨立客群再二次拆分（hippo 刀法已演練） |
| 對 hippo 的依賴 | **零依賴（A′）** | 實際依賴面僅 `lifecycle_schema.PHASES`（7 元素字串 tuple，`persona/contract.py:10`）與 `lib/idle.py`（23 行，`coordinator/manager.py:217`）——為此拉整個 31k 行記憶產品不值得。PHASES 自帶 + 主 repo 對齊測試；idle 直接 vendor |
| deck 去留 | **整包留主 repo** | #186 §6 三分裁決：現有 `deck/`（schema/compile/verify/CLI/cards）幾乎全是 lifecycle 定義層，「manager 那半」（task_type 選牌）是 Phase B 未寫；persona loader 對 deck 缺席已 fail-open（`loader.py:77`）；deck 零 import 鐵律有 CI AST lint 守著 |
| 「先二後三」的「三」 | **本次不觸發** | cortex 與 hippo 之間無值得共享的 lib 面（見 A′）；paulsha-lib 升格留待 deck Phase B 定義層歸位或出現第二個真消費者 |
| 依賴方向 | 主 repo → cortex（git+SHA pin，仿 hippo）；cortex → 無 paulsha 依賴 | 主 repo 的 bot/cockpit/core daemon 消費 `control.client`，pin 模式與 consumer contract test 先例現成 |
| CLI | cortex 自帶 console script；`psc coordinator` 改 **thin shim** 委派 | 主 repo 反正保有 cortex 依賴（control.client），shim 免費且不破壞肌肉記憶；與 hippo tombstone 情境不同（hippo 無主 repo 對其 CLI 的依賴） |

## 3. 範圍盤點

### 3.1 遷出（→ paulsha-cortex）

| 項目 | 現位置 | 規模 |
|---|---|---|
| coordinator（manager daemon、autonomy、dispatcher、registry、launcher、completion、broker_reaper、seams、contract_command、CLI） | `paulshaclaw/coordinator/` | 13 檔、2,253 行 |
| control（檔案契約控制面：constants、contract、client） | `paulshaclaw/control/` | 281 行 |
| persona（contract、loader、gate、guardrail、handoff、render、context、shadow、scope_ci + personas.yaml） | `paulshaclaw/persona/` | 815 行 + YAML |
| manager 周邊 scripts | `scripts/coordinator/`（hooks、relay hook、install-manager-units.sh、telegram notifier、dispatch script）、`scripts/service-manager.sh` | — |
| systemd 單元模板 | `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.{service,timer}.tmpl` → 改由 cortex `install service` 出貨（仿 hippo `install hooks|service`） | — |
| persona scope CI | `.github/workflows/persona-scope.yml`（跑 `python -m paulshaclaw.persona.scope_ci`） | — |
| 測試 | `test_coordinator_*`（14 檔）、`test_persona_*`（8 檔）、`test_control_*`（2 檔）、`test_start_manager_service.py`、`test_stage4_persona_contract.py` | 約 25 檔 |

### 3.2 留守（主 repo）

- `deck/` 全部（835 行）＋ deck 相關測試。
- `psc` CLI：`coordinator` 子命令改 thin shim（lazy import `paulsha_cortex` CLI）。
- `bot/listener.py:17`、`cockpit/app.py:7`、`core/daemon.py:14` 的 control.client import → 改 `paulsha_cortex.control.client`。
- W7 整合測試（import `coordinator.autonomy`）→ 改 import cortex，留主 repo（驗「deck compile 產出 ↔ manager 可解析」的跨包契約）。

### 3.3 剪線（A′ 三條）

| 線 | 處置 |
|---|---|
| `persona/contract.py` → `paulsha_hippo.lib.lifecycle.PHASES` | cortex 自帶 7 元素 PHASES 常數；主 repo 加相等性對齊測試（見 §4） |
| `coordinator/manager.py` → `paulsha_hippo.lib.idle` | vendor 23 行進 cortex（來源註記 hippo commit） |
| `paulshaclaw.config.paths` 5 函式（`control_root`/`coordinator_root`/`repo_root`/`specs_root`/`worktree_root`） | cortex 自帶 paths 模組，遵守同一 env 契約（`PSC_*` 覆寫 → `~/.agents/*` 預設）；主 repo 加等價測試 |

## 4. 契約與對齊測試（主 repo 為對齊點）

主 repo 同時依賴 hippo 與 cortex，是天然的契約交會處（現有先例：hippo-consumer 契約測試、`test_deck_contract_alignment.py`、deck spec §9.2 鏡射+相等性模式）。新增：

1. **PHASES 相等性**：`paulsha_cortex` 的 PHASES == `paulsha_hippo.lib.lifecycle.schema.PHASES`。
2. **paths 等價**：cortex paths 模組與主 repo facade 在同 env 下輸出相同路徑。
3. **deck↔persona 對齊**：`test_deck_contract_alignment.py` 續存，persona 側改讀 cortex 的 personas.yaml/loader。
4. **檔案接點不變**（不需新測試，聲明即可）：manager 只認 spec frontmatter 四欄位（`slice_id`/`dispatch`/`plan`/`depends_on`）；control plane 檔案契約在 `~/.agents/control`。deck compile 與 manager 的接點是檔案，不是 code——拆分不影響。
5. **cortex → deck 的 lazy import 方向聲明**：persona loader 的 skills shadow 驗證保留 `from paulshaclaw.deck.schema import ...` lazy import（fail-open）——這是 cortex 對主 repo 的**選配反向依賴**：standalone 安裝時 deck 缺席、靜默跳過；與主 repo 同裝時正常驗。不入 cortex 的 install_requires，僅為 runtime 可選增強。
   **效力定位（2026-07-07 對抗審查後明文化）**：shadow 驗證僅為 `warnings.warn` 等級的 lint，**不是 enforcement**——persona schema 硬驗證（raise）不依賴 deck。跨包一致性的確定性閘門是本節第 3 項的主 repo 對齊測試；兩態覆蓋由 CI 天然分擔（cortex CI 無 deck = deck-absent 路徑；主 repo CI 同裝 = deck-present 路徑）。fail-open 範圍沿 deck W5（#226）既有裁決：僅限 deck 缺席，壞目錄要警示、邏輯 bug 不吞。
6. **單寫者不變量**：control plane 既有單實例保證隨包平移——manager daemon 以 `flock` 持 `control_root()/manager.lock`（現 `coordinator/manager_daemon.py` `acquire_lock`、`control/constants.py:33`），kernel 隨行程死亡釋放、stale lock 可回收。新舊 daemon 若同時存在，第二個實例拿不到鎖即退出，重複派工在 runtime 層被阻斷。此不變量列入 cortex 測試平移必含項。

## 5. Cutover 順序（仿 #228 刀法）

- **Phase 0 — cortex repo 骨架**：pyproject、tests CI（R-19）、policy engine pin v1.0.12、tag ruleset；R-21 tier 依對外定位標 shareable（去識別化檢查隨掃描）。
- **Phase 1 — 平移 + 剪線**：三包程式碼與測試平移（保留 git 歷史可選 subtree/filter-repo，hippo 先例用何法照抄）；剪 §3.3 三條線；cortex 全測試綠。
- **Phase 2 — 主 repo 遷移刀**：刪三包；pyproject pin cortex（git+SHA）；bot/cockpit/core import 改線；`psc coordinator` shim；新增 §4 對齊測試；W7 整合測試改線；`deploy/planner.py` 移除 manager 單元模板引用；grep `paulshaclaw.persona|paulshaclaw.coordinator|paulshaclaw.control` 清零（shim 除外）。
- **Phase 3 — 本機 E2E + systemd cutover**：fresh-install 驗證（hippo 教訓：wheel 佈局 bug 只有 fresh-install E2E 攔得到）；manager systemd 單元改由 cortex 出貨並實際 cutover；complete tick 實走。
  **cutover 協議（2026-07-07 對抗審查採納）**：先 `stop && disable` 舊 manager 單元再 enable cortex 單元；cortex `install service` 必須冪等（重跑不留半套狀態）；rollback 路徑 = revert 主 repo pin + 重 enable 舊單元；E2E 加驗「舊 daemon 未停時啟動 cortex daemon」——預期第二實例因 `manager.lock` flock 拿不到鎖而退出（見 §4.6）。

## 6. 驗收（DoD）

1. `pip install paulsha-cortex` 於乾淨環境單獨可用，**不拉 paulsha-hippo**（`pip show` 依賴清單驗證）。
2. cortex repo 測試全綠；主 repo 測試全綠（含 §4 對齊測試）。
3. manager daemon 經 cortex 安裝路徑啟動，complete tick 實走通過；`psc coordinator` shim 委派正常。
4. 主 repo grep 三包 import 清零（shim/相容層除外）。
5. persona scope CI 在 cortex repo 內續跑。
6. cutover 協議實走：舊單元停用→cortex 單元 enable→complete tick；`install service` 重跑冪等；雙 daemon 鎖競爭驗證（第二實例退出）。

## 7. 非目標

- paulsha-lib 升格（deck Phase B 再議）。
- deck 任何搬移或拆分。
- G2 enforce 翻牌（#124）——**建議為拆分後 cortex 內第一個大 PR**，不混入本刀。
- hippo repo 任何變動。
- PyPI 發版（沿 hippo 前例，git+SHA pin 先行）。
- Telegram `/dispatch` 接線等 deck Phase B/C 項目。
- **control root 的多實例／租戶隔離重設計**（2026-07-07 對抗審查裁決不採納）：`~/.agents/control` per-user ambient namespace 是 hub-and-spoke 的刻意設計（單一 manager 持有任務權威，bot/cockpit/daemon 匯聚同一控制面），與 hippo `~/.agents/memory` 同一產品模型；instance 參數化已由 `__INSTANCE__` systemd 模板 + `PSC_*` env 覆寫提供。本刀為行為保持拆分，不改隔離模型。

## 8. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 拆分後緊接 G2 大改，若邊界錯會來回搬 | G2 全程落在 cortex repo 內（manager dispatch 與 persona gate 同包），拆分邊界不受影響 |
| PHASES 三處（hippo/cortex/語意文件）漂移 | 主 repo 對齊測試為強制閘；詞彙表語意已凍結（Stage 3 生命週期） |
| fresh-install 才會現形的打包 bug | Phase 3 強制 fresh-install E2E（hippo 教訓直接複用） |
| cortex PR 引用主 repo issue 觸發 R-17 | 跨 repo 引用一律掛 `policy-exempt:issue-link`（hippo 連踩兩次的教訓） |
| 本機 worktree 測試假失敗（`test_project_resolver` 等） | 判定回歸前在無變更 worktree 交叉驗證（既有教訓） |

## 9. 動工程序註記

- 開新 issue（治理包拆分，引用 #125 但不 close 它——#125 為 umbrella）；分支 `feature/<N>-cortex-extraction`。
- 主 repo 遷移刀 PR body `Closes <新 issue>`；R-09 code PR 掛 `skip-changelog`。
