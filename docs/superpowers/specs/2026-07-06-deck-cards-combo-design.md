# skill/persona 卡片化（deck）設計 — #186 Phase A 執行設計

> 真相源：本檔為 #186 Phase A 的執行設計。背景評估與裁決過程見 #186 issue body（2026-07-06 回填）。已含 2026-07-06 Codex 對抗審查修正（7 Important + 1 Minor 全數採納）。
> 相關：#187（manager control-plane，已通電）、#138/#140/#142（計分/成本/task_type，Phase C 掛點）、#23（/dispatch stub，Phase B 收）、#125／`memory-extraction-hippo`（協調見 §9）。

## 1. 目標

把 `feature-delivery-pipeline`（散文版 11-phase router）與 `mcu-coding-skill` 轉譯成機器可讀的卡片（card）與組合技（combo），並提供 combo 編譯器把「一句 task + 一張 combo」展開成既有 manager 可代管的 slice specs。**manager runtime 零改動**：接點是檔案（編譯產出的 specs），不是 code。

Phase A DoD：`psc deck compile feature-oneshot --task "..." --emit` 產出的 specs 能被 `scan_specs` 解析、`detect_cycles` 無環、在 `dispatch: hold` 下 `ready_units` 為空（不誤觸發）。

## 2. 決策記錄（2026-07-06 session 已裁決）

| 裁決 | 內容 |
|---|---|
| 方案 | 薄宣告層 + 編譯器（deck 包）；否決 manager 內建 combo runtime（動 runtime、重複 Stage 3）與維持散文 router（無選牌/計分/成本掛點） |
| 命名 | 新包 `paulshaclaw/deck/`（牌組容器隱喻：cards + combos 都住 deck 裡） |
| 歸屬 | 定義與驗收（schema/compile/verify）走 lifecycle 性質的宣告層；選牌與執行留 manager——Phase A 只做前者 |
| hippo 協調 | deck 對 `paulshaclaw.lifecycle`／`paulshaclaw.memory` **零 import**（§9） |
| 安全預設 | compile 預設 dry-run；`--emit` 產出一律 `dispatch: hold` |
| additive | 使用者指定卡預設併入手牌不取代骨幹；排他需 `--only` |
| 檔案佈局 | 卡片集中 `cards.yaml` 一檔；combo 每檔一個；Phase A 全落主 repo，custom-skills frontmatter 回灌留 Phase B |

## 3. 全景架構

### 3.1 deck 包結構

```
paulshaclaw/deck/
├── __init__.py
├── schema.py        # Card / Combo dataclass + validator（fail-closed，仿 persona loader）
├── compile.py       # combo + task → slice spec 檔（W3，含 additive 規則）
├── verify.py        # 卡片 produces glob 驗收器（W4）
├── cli.py           # deck 子命令實作（掛入 psc 需同步改 paulshaclaw/cli.py，見下）
└── data/
    ├── cards.yaml             # skill 卡目錄（集中一檔）
    └── combos/
        ├── feature-oneshot.yaml   # W1：轉錄自 feature-delivery-pipeline 11 phases
        └── mcu-feature.yaml       # W2：轉錄自 mcu-coding-skill
```

註：現行 `paulshaclaw/cli.py` 只路由 `{memory|coordinator}`、未知命令 exit 2（cli.py:6/:16）。**W3 範圍明列**：修改 `paulshaclaw/cli.py` 新增 `deck` route 與 usage，並更新 `tests/test_psc_cli.py`（含 unknown-command 回歸）。

### 3.2 依賴方向鐵律

- `deck` 對 `paulshaclaw.lifecycle`、`paulshaclaw.memory` **零 import**（§9.1）。schema 驗證、glob 比對、frontmatter 產生全部自足（dataclass + fnmatch + yaml）。
- `coordinator` **不** import `deck`。Phase A 兩系統唯一交點是編譯產出的 spec 檔。
- 路徑解析經 `paulshaclaw/config/paths.py` facade（#91／PR #213），deck 內不得新增 `Path.home()`（§9.2）。
- persona 卡不複製資料：由 loader 以 `personas.yaml` 的 `PersonaContract` 為源即時衍生 view，cards.yaml 只收 skill 卡。

## 4. 資料模型

### 4.1 Card（skill 卡，cards.yaml）

```yaml
cards:
  - id: writing-plans
    kind: skill                    # Phase A 僅 skill；persona 卡由 personas.yaml 衍生
    type: interactive              # interactive | headless
    class: core                    # core | niche | emergency（core/emergency 永不 park，Phase C 用）
    skill_ref: "superpowers:writing-plans"
    requires:
      - "openspec/changes/<change>/proposal.md"
    produces:
      - "docs/superpowers/plans/*-<task-slug>.md"
    persona_binding: planner       # 對應 personas.yaml role；可空
    provider_binding: null         # Phase C 掛點，Phase A 一律 null
```

欄位語意：
- `type: interactive` 卡在互動 session 內執行（可自由迭代多輪）；`type: headless` 卡才會被編譯成 slice spec。
- `requires` / `produces` 是 artifact glob，佔位符僅允許 `<task-slug>`、`<change>` 兩個，由 compile 代入。
- `produces` 是 verify 的驗收依據，只寫 gate engine 可機械驗證的路徑，不寫語意條件。
- **`requires`/`produces` 僅作用於 compile-time 檢查與 `deck verify` 報告——runtime 派工不讀它們**（manager 只認 frontmatter 四欄位，`autonomy.py:167` 的 ready 條件只看 `slice_id`/`dispatch`/`plan`/`depends_on`）。機器強制 gate（翻 auto 前自動驗收）屬 Phase B。

### 4.2 Combo（combos/*.yaml）

```yaml
combo:
  id: feature-oneshot
  task_type: feature               # #142 taxonomy 對齊點（Phase B 選牌 key）
  cards:
    - ref: brainstorming           # 依序；headless 卡可帶 depends_on 形成 DAG
    - ref: openspec-propose
    - ref: writing-plans
    - ref: oneshot-build
      depends_on: [writing-plans]
    - ref: code-review
      depends_on: [oneshot-build]
    # ...
  gate_spine:                      # artifact 檢查點骨幹（非逐步腳本）
    - after: writing-plans
      exists: ["docs/superpowers/plans/*-<task-slug>.md"]
```

### 4.3 W0 對齊義務（frontmatter 真相源）

emitted spec 的 frontmatter 欄位**以 `coordinator/autonomy.py::parse_spec_frontmatter` 實際接受的欄位為準**（`dispatch`／`slice_id`／`plan`／`depends_on`），W0 第一項工作是核對該契約並寫進 schema 測試；不得發明 runtime 會忽略的欄位。persona binding 若 runtime 契約無對應欄位，記在 spec 內文（plan 參照段），不塞 frontmatter。

## 5. compile 語意（W3）

```
psc deck compile <combo> --task "<描述>" [--change <name>]
    [--with <card>[:after=<id>|:before=<id>]]... [--only <card>...]
    [--allow-external] [--out <dir> | --emit [--force]]
```

佔位符代入：`<task-slug>` 由 `--task` 正規化而來（限 `[a-z0-9-]`、長度 ≤ 60、branch-safe——它將成為 `feature/<slice_id>` 的一部分）；卡片用到 `<change>` 而未給 `--change` → 報錯。

1. 載入 combo + cards（fail-closed：壞檔、未知 `ref`、combo 內 `depends_on` 成環 → 整批拒絕，不產任何檔）。
2. `type: interactive` 卡編為**前置 checklist**（輸出到 stdout／compile 報告），其 `produces` 成為首個 headless slice 的 requires 與 `plan` 參照；`type: headless` 卡逐張產 slice spec，`slice_id = <task-slug>-<card-id>`。
3. **additive 規則**：`--with <card>` 把指定卡併入手牌，**不取代骨幹**；`--only` 才是排他模式（對應使用者說「只用」）。插入位置優先採顯式 `:after=<id>`／`:before=<id>`；未指定時僅在保守 pattern 覆蓋檢查可證明時自動插入（requires glob 與上游 produces glob 字面前綴一致至首個 wildcard），無法證明 → fail-closed 要求明示位置。
4. 輸出安全：預設 dry-run 印到 stdout；`--out <dir>` 寫任意目錄；`--emit` 才寫活佇列，且 **`dispatch:` 一律 `hold`**。
   - specs 目錄解析**鏡射 manager 現行契約**（`PSC_MANAGER_SPECS_DIR` env → `~/.agents/specs`，同 `manager_daemon.py:101` 優先序），以 deck 內單一 helper 實作，並附「與 manager 預設相等」的回歸測試；P2 facade（#91／PR #213）落地後提案補 `specs_dir()` 欄位再一行切換（現行 facade capability 清單無此欄位）。
   - emit 檔名固定 `<slice_id>.md`、**flat 不建子目錄**（`scan_specs` 為非遞迴單層掃描，autonomy.py:98）；同名檔已存在 → 預設拒絕並報錯（防覆蓋 in-flight slice，`detect_cycles` 對重複 slice_id 亦會 fail），`--force` 才原子覆蓋。
   - **hold 保證的精確範圍**：`dispatch: hold` 保證不進 **automatic** ready/fanout（`ready_units` 實證，autonomy.py:181）；manager control-plane 的手動 `dispatch` request（含 `force_hold` 覆寫，manager_daemon.py:262/:279）是 operator 明示動作，視為授權行為，Phase A 不擋。
5. 錯誤處理（編譯期為 pattern-level 檢查，非檔案存在性——task 尚未執行）：每張卡的 `requires` glob 必須被上游卡（含 interactive 前置與 `--with` 併入卡）的 `produces` pattern 覆蓋，否則列為 external input 並要求 `--allow-external` 明示放行；未放行的缺口 → 明確報錯列出，不產檔。

## 6. verify 語意（W4）

```
psc deck verify <card-id> --task-slug <slug> [--root <dir>]
```

對單張卡做 `produces` glob 存在性驗收，回報 pass/fail 與缺失清單；exit code 供 CI／gate 使用。純 fnmatch/pathlib 實作，不 import lifecycle（§9.1）。它是未來 gate engine 的 deck 端原語，Phase A 只做「存在性」，不做內容驗證。

作業程序約定（Phase A 為人工紀律，機器強制留 Phase B）：operator 把 emitted spec 從 `hold` 翻 `auto` 前，先跑 `psc deck verify` 確認前置卡 produces 到位；compile 的 emit 報告會印出這份 checklist。

## 7. personas 接線（W5）

`personas.yaml` 各 role 新增 `skills:` 欄位（list of card id）；`loader.py`／`contract.py` 擴充：載入時驗證引用的 card id 存在於 `cards.yaml`，缺失→ warning（**shadow，不 enforce**，與現行 `enforcement: shadow` 一致）。不改 guardrail 行為。

對抗審查已驗證：現行 validator 不會因 unknown key 拒絕（`contract.py:80` 只檢 required/type），但 **loader 構造 `PersonaContract` 時會丟棄未知欄位（`loader.py:53`）**——W5 需同步讓 loader 讀取並保留 `skills:`，否則欄位加了也是靜默蒸發。

## 8. 測試與驗收

- W3／W4 走 TDD（RED 先行）；schema fail-closed 路徑（壞 YAML、未知 ref、成環、佔位符打錯）各有測試。
- **W7 整合驗證（parse-level，不真派工）**：用 W1 真卡片編譯 → `scan_specs` 解析綠、`detect_cycles` 無環、`ready_units` 在 hold 下為空。整合測試住主 repo `tests/`，import `coordinator.autonomy`。
- **W7 import 鏈註記（對抗審查修正）**：`import paulshaclaw.coordinator.autonomy` 會觸發 package `__init__` 的 eager import 鏈（`__init__` → `cli` → `manager` → `paulshaclaw.memory.dream.idle`；`autonomy` → `contract_command` → persona/lifecycle），故 W7 **今日**會間接觸及 memory/lifecycle，hippo §4.2 改寫後轉為 `paulsha_hippo.lib.*`。這是 tests 層的間接依賴，不違反 deck 包零 import 鐵律；**不**為此精簡 coordinator `__init__`（守住 runtime 零改動），W7 測試中不得直接 import `paulshaclaw.memory`／`paulshaclaw.lifecycle` 字面（hippo §4.5 清零相容）。
- CI：既有 tests workflow 自然涵蓋（R-19）；新增測試檔隨 W3/W4/W7 進 `tests/`。

## 9. 與 hippo 拆分（#125／memory-extraction-hippo）的協調

| 接觸面 | 處置 |
|---|---|
| hippo §4.5「grep `paulshaclaw.lifecycle`/`paulshaclaw.memory` 清零」+ §4.6 import 面 CI | **9.1 零 import 鐵律**：deck 不 import 兩者，完全退出 hippo §4.2 改寫清單與清零範圍。未來需共用原語時走 cutover 後的 `paulsha_hippo.lib.*`（屆時主 repo 已有 SHA pin 依賴） |
| PR #213（#91 facade）收斂 `Path.home()` | **9.2 facade 對齊（對抗審查修正）**：facade capability 現行清單**無 `specs_dir`**（只有 repo/memory/agents/config/worktree root）。deck 先以內部單一 helper 鏡射 manager 契約（`PSC_MANAGER_SPECS_DIR` → `~/.agents/specs`）+ 相等性測試；#213 落地後提案在 facade 補 `specs_dir()` 再切換。deck 內不散落 `Path.home()` |
| hippo §4.2 改寫 `persona/contract.py` import；W5 亦動 `persona/{loader,contract}.py` | **9.3 merge 順序註記**：不同行、可合併；先落地者贏、後者 rebase。時序推估 W5 先（hippo §4 受站穩閘 + 2 週約束） |
| 編譯目標契約（spec frontmatter）與 W7 依賴的 `coordinator.autonomy` | coordinator 不在 hippo Phase 1 範圍（Phase 2 明文傾向留主 repo）→ 契約穩定。惟 W7 經 coordinator import 鏈**間接**觸及 memory（§8 註記），hippo §4.2 改寫後自然轉軌 |
| `psc` CLI：hippo §4.5 移除 memory 子樹；deck 新增 `deck` 子樹 | 不同子樹，衝突面僅 entry 註冊行，trivial merge |

## 10. 工作拆解與平行派工（W0–W7）

| # | 工作項 | 邊界 | 依賴 |
|---|---|---|---|
| W0 | schema v0 凍結：Card/Combo 欄位、YAML 格式、佔位符、§4.3 frontmatter 對齊測試 | schema.py + schema 測試 | —（barrier，單點先行） |
| W1 | `feature-delivery-pipeline` → cards.yaml 11+ 張卡 + `feature-oneshot.yaml` | data/ 新檔 | W0 |
| W2 | `mcu-coding-skill` → `mcu-feature.yaml`（+ 增補 MCU 特有卡） | data/ 新檔 | W0 |
| W3 | compile.py + additive/--only + CLI + TDD | deck 包（compile/cli）**+ `paulshaclaw/cli.py` deck route + `tests/test_psc_cli.py`** | W0；`--emit` 段依 §9.2 對齊 #213 |
| W4 | verify.py + CLI + TDD | deck 包（verify），與 W3 不同檔 | W0 |
| W5 | personas.yaml `skills:` + loader 驗證（shadow） | persona 包 | W0 |
| W7 | 整合 dry-run（parse-level）+ integration_test_gate | tests/ | W1+W3（W2/W4/W5 可後併） |

W1–W5 五條 lane 互不撞檔，各自 branch/worktree 平行開發；W7 為整合節點。W2 兼任 schema 泛化性壓力測試（第二個實例暴露隱藏假設）。

## 11. 風險與對策

- **卡片 metadata 與 SKILL.md 散文漂移**：欄位極簡、produces 只寫可機械驗證路徑；SKILL.md 保持人讀真相源，卡片是 dispatch 投影（Phase B 回灌 frontmatter 時再單一源化）。
- **schema 過早凍結**：W2 第二實例當壓力測試；schema 版本欄（`version: 0`）預留遷移。
- **specs 活佇列誤觸發**：hold-by-default + 預設 dry-run 雙保險（§5.4）；hold 保證範圍以 automatic 路徑為限（手動 `force_hold` 屬 operator 授權行為，見 §5.4）。emit 同名拒絕 + `--force` 防覆蓋 in-flight slice。
- **與 hippo 撞檔**：§9 三條處置後，唯一交點是 persona 包不同行的兩次編輯。

## 12. 非目標（Phase A 明確不做）

- 選牌自動化（task_type → combo，等 #142 taxonomy）
- Telegram `/dispatch` 接線（#23，Phase B）
- hit ledger／park／janitor（skill registry 自治理，Phase C）
- `provider_binding` 生效（#140，Phase C）
- custom-skills SKILL.md frontmatter 回灌（Phase B）
- coordinator／manager 任何 runtime 改動
- persona enforce 翻牌（#124 另行）
