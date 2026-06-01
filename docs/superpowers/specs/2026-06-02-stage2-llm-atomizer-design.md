# Stage 2 — Topic 3.2：LLM 語意 Atomizer（Promoter 升級）設計

- 日期：2026-06-02
- 範圍：T3.2 — 把 T3 atomizer 的確定性 `Promoter` 換成 LLM 語意實作(per-session 語意拆分/合併 + tag + relations)
- 前置：T1/T2/T3/T4/T8 ✅、Stage 3 schema ✅
- 後續解鎖：Topic 5(dream 排程 + 跨 session 演進脈絡 + 全域實體圖)、Topic 7(retrieval 消費語意 relations)
- 後續優化：**SkillOpt 迴圈**(獨立後續,掛 `evolve`)——把種子 skill 練到 gemma4 能完美執行
- 依據：merged T3(`paulshaclaw/memory/atomizer/`)、`hamanpaul/custom-skills` 的 `obsidian-atomize`、`microsoft/SkillOpt` 概念、`paulshaclaw/lifecycle/schema.py`

---

## 1. 範圍與邊界

### In scope
1. **① 種子原子化 skill 文件** `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`:改寫自 `obsidian-atomize` 的 6 階段 + 從 `~/notes/TechVault`(120)、`WorkVault`(29)共 ~149 個 `atomized_from` 範例**反推的拆分原則**(只萃取原則、不抄原文;PersonalVault 0 範例且涉隱私,排除)。手寫種子版,之後由 SkillOpt 優化。
2. **② `LLMPromoter`**(實作 T3 `Promoter` seam,介面擴為 **per-session**):讀①的 skill + session fragments → 經 agent_exec 拿結構化 JSON → 組 slices。
3. **`agent_exec` 後端**:config 可設定、subprocess 一次性叫起的 agent 命令(預設 `scripts/claude-gemma4`,地端 vLLM,零 API/走訂閱)。與 paulshiabro `/agent` 共用同一 command 設定。
4. **語意產物**:每 slice 帶 `artifact_kind` + 精準 project 歸屬(從已知 project 清單選)+ `tags` + session 內/已知實體 `relations`;仍經 `slice_frontmatter` 賦**內容派生** `slice_id`/`checksum` 並雙重驗證(Stage3 ∪ T4)。
5. **fail-closed**:agent 不可用/JSON 壞/schema 不過 → session 留 `split`、warn、隔日重試。

### Out of scope
- ❌ **SkillOpt 優化迴圈**(critic + validation set + 迭代)→ 獨立後續,掛 `evolve`。
- ❌ 跨 session 演進脈絡 + 全域實體圖(MTK/BRCM…)→ Topic 5。
- ❌ dream 排程器(5am cron)→ Topic 5。
- ❌ 改 T3 的 splitter/ledger/flow-through/pipeline 骨架——只換 Promoter 實作 + 加 agent_exec + skill。
- ❌ 新 API/SDK client、tmux 活 pane dispatch。

### 硬約束(沿用 T3)
- 不擴充 Stage 3 schema(`tags` 是 Stage-2 自有欄位;新語意 relation edge 加在 relations.jsonl)。
- slice 過 `lifecycle.schema` ∪ T4 契約。
- idempotency 靠 processing ledger(promote 一次)+ LLM 輸出 cache;重匯入才重跑。
- **可測性**:agent_exec 是外部非確定性程序 → 注入 fake client / stub 命令做確定性測試;真 exec 走 opt-in。

---

## 2. 架構與元件

沿用 `atomizer/`,只換 Promoter 實作 + 加 LLM 元件。`/agent`(`core/commands.json`,管 **tmux 長駐 session**)與 T3.2(**一次性 headless**)共用 command 設定,但呼叫模式不同;`/agent` 的 tmux 故障若存在屬獨立 debug,不阻塞 T3.2。

```
paulshaclaw/memory/atomizer/
├── skills/atomize-knowledge-slice.md   # ① 種子 skill(改寫自 obsidian-atomize + vault 提煉)
├── agent_exec.py        # AgentClient 介面 + AgentExecClient(subprocess 一次性) + FakeAgentClient
├── prompt.py            # 載入 skill + fragments + 已知 projects → 組 prompt
├── llm_output.py        # 解析/驗證 agent JSON → SliceProposal[]
├── llm_promoter.py      # LLMPromoter(per-session):exec→parse→build→雙重驗證
├── promoter.py  (改)    # Promoter ABC 介面改 per-session;IdentityPromoter 配合
├── pipeline.py  (改)    # promote_pass 整 session 餵 promoter;promoter 可注入;LLM 輸出 cache
├── config.py/atomizer.yaml (改) # agent_exec(command/timeout/model)、promoter 選擇、known_projects 來源
└── cli.py       (改)    # atomize 增 --promoter llm|identity
```

| 元件 | 職責 | 依賴 | 介面 |
|---|---|---|---|
| `skills/…md` | 教 agent 如何拆/合併/打 tag/建關聯(種子) | — | (文件) |
| `agent_exec.py` | 一次性 subprocess 叫 config 命令,timeout,捕 stdout | subprocess | `AgentClient.run(prompt)->str`;`FakeAgentClient` |
| `prompt.py` | 組 prompt(skill + fragments + projects) | skills、config | `build(skill, fragments, projects)->str` |
| `llm_output.py` | 抽 JSON + schema 驗證 | json | `parse(raw)->list[SliceProposal]` |
| `llm_promoter.py` | exec→parse→`slice_frontmatter` | 上面 + slice_frontmatter | `promote(fragments, config)->list[Slice]` |
| `promoter.py`(改) | `Promoter.promote(fragments, cfg)` per-session | — | ABC |
| `pipeline.py`(改) | promote_pass 整 session;cache;relations | promoter, ledgers | `run(..., promoter=...)` |

**介面變更(唯一動到 T3 骨架):** `Promoter.promote` 從 `(fragment)` → `(fragments: list[Fragment])`;`IdentityPromoter` loop fragments 仍 1:1;`pipeline.promote_pass` 整 session 傳。向後相容。

**Stage 1 接觸面(有界):** `/agent` 遷移到讀共用 `agent_exec.command`(僅 config 統一)。

**可測性:** `LLMPromoter` 吃注入的 `AgentClient`;測試用 `FakeAgentClient` 或 stub 命令 → 全確定性;真 `AgentExecClient` 走 opt-in。

---

## 3. 資料模型

> 承 T4 教訓:ledger `ts` 用注入 `now`。

### A. 種子 skill 文件
提煉自 obsidian-atomize 6 階段 + TechVault/WorkVault 149 範例。含:拆分原則(單一概念一 slice、跨 fragment 同概念合併、最小原子大小、共用前言、命名)、project 歸屬指引(從已知清單選否則 `_unknown`)、tag 策略(全域 vs 概念)、relation 指引(session 內互連 + 已知實體 mentions)、**強制輸出契約(下方 B)**。

### B. LLM 輸出 JSON 契約
```json
[
  {
    "title": "pwhm fsm states",
    "artifact_kind": "report",          // ∈ Stage3 ARTIFACT_KINDS
    "project": "prplos-core",           // ∈ 已知 projects 或 "_unknown"
    "tags": ["pWHM", "fsm"],
    "body": "…蒸餾 markdown…",          // 非空
    "source_fragment_indices": [0, 1],  // 可合併多 fragment
    "relations": [
      {"type": "relates_to", "target_title": "pwhm vendor hooks"},
      {"type": "mentions", "entity": "BRCM"}
    ]
  }
]
```
`llm_output.parse` 驗證型別、`artifact_kind` 合法、`project` 在清單、`body` 非空;任一不過 → fail-closed。

### C. SliceProposal → Slice
- `checksum = sha256(body)`;**`slice_id = sl-<sha256("<agent>|<session>|"+sha256(body))[:16]>`**(內容派生)。
- frontmatter = T3 union(Stage3 ∪ T4)**+ `tags`**;`distilled_from`=session;`source_fragments`=indices。
- 過 `slice_frontmatter.validate`(Stage3 ∪ T4)。

### D. 新增欄位 / 邊
- slice frontmatter 加 **`tags: [...]`**(Stage-2 自有,Stage3 不拒額外欄位)。
- `relations.jsonl` 新語意邊:`relates_to`(slice→slice)、`mentions`(slice→`entity:<NAME>`);T3 既有確定性邊照舊。

### E. 重匯入 / stale
- 內容派生 slice_id:同內容→同 id;內容變→新 id。重匯入產新 slice,舊的 stale → **交 T4 janitor decay**,不在 T3.2 處理。

### F. processing.promoted 加欄位
`promoter="llm"` + `model` + `skill_hash`(skill 文件 sha256)——供日後 SkillOpt 把品質對應 skill 版本/模型。

---

## 4. 資料流

### promote_pass 改動
T3 逐 fragment 1:1 → T3.2 **整 session 一次**:`promoter.promote(該 session 全部 fragments) -> list[Slice]`(slices 數可 ≠ fragments 數)。

### LLMPromoter.promote(fragments, config)（純邏輯 + 注入 AgentClient)
```
1. load skill + 已知 projects(~/.agents/config/projects.yaml)
2. fragments_hash = sha256(sorted fragment bodies)
3. raw = cache.get(session_key, fragments_hash) or agent_client.run(prompt.build(...))
4. proposals = llm_output.parse(raw)
5. for proposal: slice = slice_frontmatter.build_from_proposal(...); validate → 有錯 raise
6. return slices(每 Slice 帶 relations[],target 在 batch 內解析)
```
**fail-closed = session 粒度 all-or-nothing**:任一失敗 → raise → promote_pass 留 session 在 split、warn、不寫 slice。

### promote_pass 每 session 步驟順序(crash-safe)
```
1. 取/算 LLM 輸出(cache 命中重用,否則呼叫並寫 cache)
2. 組 + 驗證所有 slices(in-memory;任一壞 → 整 session fail-closed)
3. 原子寫 knowledge slice
4. relations.append:promoted_to(每 source fragment→slice)、distilled_from(slice→session)、
                    relates_to(slice→batch 內 target slice_id;解析不到跳+warn)、mentions(slice→entity:NAME)
5. processing.append(state=promoted, promoter=llm, model, skill_hash)
6. 搬 fragments → archive
7. 清該 session cache
```

### crash-resume cache
`runtime/cache/atomize/<session_key>__<fragments_hash>.json` 存原始 LLM 輸出。命中即重用 → 重跑不重叫 LLM、輸出不漂移、slice_id 穩定;promoted 後清。cache 損壞視為 miss(重叫),不 fail。

### 決定性
`now` 注入;LLM 非確定性但首次 promote 後**凍結**(processing gate + cache);slice_id 內容派生。

### 與 IdentityPromoter 共存
`--promoter identity|llm` 選;IdentityPromoter per-session 後 loop fragments 仍 1:1、relations=[];promote_pass 對兩者一致(讀 `slice.relations`)。

---

## 5. 錯誤處理 & Guardrails

| 失敗 | 處置 |
|---|---|
| agent 命令缺/不可執行、timeout、非零退出、空 stdout | **fail-closed**(session 留 split) |
| 無 JSON / JSON 壞 / schema 不過(型別/artifact_kind/project/body 空) | **fail-closed** |
| slice 驗證(Stage3/T4)不過 | **fail-closed**(整 session all-or-nothing) |
| cache 損壞 | 視為 miss、重叫,**不 fail** |
| `relates_to` target 解析不到 | **跳該邊 + warn**,不 fail;`mentions` 永遠可寫 |
| `agent_exec` config 缺/無效 | **fail-closed** |

log → `atomizer.log`,**絕不記 LLM 原始輸出/session 內文**(只記失敗類別 + session_key + skill/config hash)。

| # | Guardrail | 保證 |
|---|---|---|
| G1–G7 | 沿用 T3(不擴 Stage3 schema、不動 T2、flow-through archive、slice 有 provenance、append-only、決定性、記錄在冊) | — |
| G8 | agent_exec 一次性無跨呼叫狀態 | 每 session fresh subprocess,不混專案內容 |
| G9 | session 粒度 all-or-nothing | 任一 proposal 不過 → 整 session 不落地 |
| G10 | LLM 輸出凍結 | cache + processing gate |
| G11 | 輸入已 redacted、不重掃 | fragments 來自 inbox(過 T8 `raw_to_distilled`);**明列的已知限制**——未來 `distilled_to_canonical` policy pass 再補 |
| G12 | 行為只在 skill 文件 | 原子化邏輯住 skill(SkillOpt 標的),prompt.py 只組裝 |

---

## 6. 測試策略

agent_exec 外部 + 非確定性 → **注入 `FakeAgentClient` / stub 命令(回罐裝 JSON)→ 全確定性**;真 gemma4 走 opt-in。

### 單元
| 測試檔 | 覆蓋 |
|---|---|
| `test_llm_output.py` | 解析合法陣列、從圍欄/散文抽 JSON、拒絕壞 JSON/缺欄位/artifact_kind 非法/project 不在清單/body 空 |
| `test_atomizer_prompt.py` | prompt 含 skill + fragments + projects;決定性 |
| `test_agent_exec.py` | stub 命令回 stdout、timeout/非零/命令不存在 raise;FakeAgentClient |
| `test_slice_frontmatter.py`(擴) | `build_from_proposal`:union+tags、內容派生 slice_id、checksum、過 Stage3∪T4 |
| `test_llm_promoter.py` | Fake 2-slice→2 Slice+relations;合併 2→1;壞輸出 fail-closed |
| `test_atomizer_promoter.py`(改) | IdentityPromoter per-session、仍 1:1 |

### Pipeline / E2E（Fake / stub）
| 場景 | 斷言 |
|---|---|
| promote_pass(LLM fake) | slices 寫出、relates_to/mentions 進 relations、processing 記 promoter=llm+skill_hash+model |
| crash-resume cache | 模擬中斷 → 重跑重用 cache(fake 只被叫一次) |
| 合併 | 2 fragment → 1 slice |
| fail-closed | fake 壞 → session 留 split、零 slice |
| flow-through | working 區空、archive 有 |
| 跨 stage 契約 | slice 過 `lifecycle.gate` |

### opt-in + 整合
- `test_atomizer_llm_live.py`:`@skipUnless(PSC_ATOMIZE_LIVE)` 跑真 claude-gemma4。CI 不跑。
- `stage2_integration_check.sh` 加 `atomize --promoter llm --dry-run`,`agent_exec.command` 指 stub fixture script → CI 確定性走完整 LLM 管線。
- skill 文件存在 + 輸出契約段落測試。
- 回歸:`unittest discover -s paulshaclaw/memory/tests` 與 `tests/` 全綠。

> 種子 skill 從 vault 提煉是 plan 的 authoring task(讀 TechVault/WorkVault 樣本 → 萃取原則 → 寫 skill),非自動化測試。

---

## 7. 解鎖的後續（非本 change 範圍）
- **SkillOpt 迴圈**(掛 `evolve`):TechVault/WorkVault 149 範例當 validation set,critic 模型迭代改 skill 文件 → best_skill.md,T3.2 runtime 永遠讀當前最佳版。
- **Topic 5 dream**:5am 排程跑 atomize + 跨 session 演進脈絡 + 全域實體圖(MTK/BRCM…)。
- **Topic 7 retrieval**:消費 `relations.jsonl`(含語意邊)+ knowledge slices。
