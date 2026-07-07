# paulsha-cortex 拆分設計（治理包 persona + coordinator + control 外部化）

> 真相源：本檔為 #125 Phase 2（治理包）拆分的架構設計。裁決過程見 2026-07-07 session（brainstorming 流程）。
> 相關：#125（切包 umbrella，Phase 2 定義處）、#186 §6（deck 歸屬三分裁決）、#124（G2 enforce 翻牌，本次非目標）、`2026-07-06-memory-extraction-hippo-design.md`（Phase 1 刀法先例）。

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
