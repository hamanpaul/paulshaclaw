# Stage 2 — Topic 3：Atomizer / Linker（確定性 MVP）設計

- 日期：2026-05-31
- 範圍：Stage 2 Topic 3（inbox→knowledge 晉升管線:確定性結構拆分 + 1:1 升級 + processing/relations ledger）
- 前置：Topic 1（記憶基底樹）✅、Topic 2（Importer）✅、Topic 8（治理層）✅、Topic 4（lifecycle/janitor）✅、Stage 3（lifecycle schema）✅
- 後續解鎖：Topic 7（Retrieval 消費 relations + knowledge slices）
- 後續升級：**T3.2**（把 Promoter 換成 LLM:語意拆分/合併 + 建關聯 + 打 tag）
- 依據：`openspec/specs/stage2-memory-governance/spec.md`、`docs/research/02.*`、`paulshaclaw/lifecycle/schema.py`（Stage 3 schema）

---

## 1. 範圍與邊界

### In scope（確定性、無 LLM）
1. **確定性結構拆分器**:讀 T2 raw session 文件,按結構邊界(turn/heading/artifact 標記)機械式切成 fragments。
2. **Flow-through + archive**:每層處理完把輸入移出工作區 → archive(working 區乾淨、provenance 保留)。
3. **Promoter（1:1 placeholder,放介面後）**:fragment → 1 個 knowledge slice,賦 Stage-3 合規 frontmatter。T3.2 換 LLM 實作。
4. **processing ledger**（`runtime/ledger/processing.jsonl`):每個 `<agent>:<session>` 狀態機 ingested→split→promoted。
5. **relations**（`runtime/ledger/relations.jsonl`):派生邊(fragment→session、slice→fragment、slice→session、supersedes),供 T7 relation traversal。
6. **CLI 一次性入口**（比照 janitor:`psc memory atomize ...`)。
7. 產出符合 **T4 讀取契約** + 通過 **Stage 3 `lifecycle.schema` 驗證**。

### Out of scope
- ❌ **LLM 語意拆分 / 語意關聯 / 打 tag**（T3.2,只換 Promoter 實作）
- ❌ work-centric 進階聚合/correlation（MVP 走 raw→fragments→knowledge 直線）
- ❌ retrieval/index（T7）、embedding/vector/graph
- ❌ 新增 **agy/gemini adapter**（T2 的事;T3 對 agent 不可知）

### 硬約束
- **不擴充 Stage 3 frontmatter schema**:T3 只「賦值」slice_id/artifact_kind/checksum/supersedes,schema 由 Stage 3 `lifecycle/schema.py` 擁有並驗證。
- **不動 T2 importer**:純 post-import。
- **flow-through 但不毀證據**:消耗掉的輸入 move 到 archive(滿足 governance「inbox 保留原始」),非刪除。
- **決定性**:MVP 全程無隨機、無 LLM、可復現(slice_id/checksum 由內容決定性導出;`now` 注入)。

---

## 2. 架構與元件

核心原則:**純邏輯（splitter/promoter）與 IO/orchestration（pipeline/ledger）分離**。

```
paulshaclaw/memory/
├── atomizer/
│   ├── splitter.py          # 確定性結構拆分:raw session 文字 → list[Fragment]（純邏輯）
│   ├── promoter.py          # Promoter 介面 + IdentityPromoter(1:1 MVP);T3.2 加 LLMPromoter
│   ├── slice_frontmatter.py # 建 knowledge slice 的「聯集 frontmatter」+ slice_id/checksum/映射 + 雙重驗證
│   ├── pipeline.py          # orchestrator:split→archive raw→promote→archive fragments→寫 ledger/relations
│   ├── cli.py               # psc memory atomize [--dry-run]
│   └── config.py            # 拆分邊界規則 / 映射表 loader（沿用 policy/janitor loader 模式）
└── ledger/
    ├── processing.py        # processing.jsonl 狀態機(ingested→split→promoted)+ flock
    └── relations.py         # relations.jsonl 派生邊 IO + traversal + flock
```

| 元件 | 職責 | 依賴 | 主要介面 |
|---|---|---|---|
| `atomizer/splitter.py` | 按結構邊界切 fragments | 無(純文字) | `split(session_doc) -> list[Fragment]` |
| `atomizer/promoter.py` | Fragment → Slice(s);MVP 1:1 | slice_frontmatter | `Promoter.promote(fragment) -> list[Slice]` |
| `atomizer/slice_frontmatter.py` | 建聯集 frontmatter、算 slice_id/checksum、映射、雙重驗證 | `lifecycle.schema`(Stage 3) | `build_slice_frontmatter(...)` / `validate(...)` |
| `atomizer/pipeline.py` | 一輪 atomize:split/promote 兩 pass | 上列全部 + processing + relations | `run(memory_root, ..., dry_run)` |
| `atomizer/cli.py` | 一次性入口 | pipeline, config | `atomize` subcommand |
| `ledger/processing.py` | `<agent>:<session>` 狀態機 | stdlib + flock | `append_state()` / `fold_states()` / `state_of(key)` |
| `ledger/relations.py` | 派生邊 append/read/traversal | stdlib + flock | `append_edge()` / `neighbors(node)` / `read_edges()` |

**跨 stage 依賴（刻意）:** `slice_frontmatter` 匯入 Stage 3 `lifecycle.schema`（`validate_frontmatter` / `compute_checksum` / `ARTIFACT_KINDS` / `PHASES`）當契約。

**兩層 frontmatter:**
- **Fragment**（inbox/_slices,輕量):memory_layer + project + source_agent/session + source_artifact + captured_at + provenance + `fragment_index` + `parent_session_ref`。
- **Knowledge slice**:T4 契約欄位 **∪** Stage 3 必填。

---

## 3. 資料模型

> 承 T4 教訓:所有 ledger 的 `ts` 用**注入的 `now`**（非 wall-clock）。

### A. Fragment 記錄（`inbox/_slices/<project>/<agent>__<session>__<NNN>.md`)
```yaml
memory_layer: inbox
project: <project>
source_agent: claude|codex|copilot|agy
source_session: <sid>
source_artifact: research|plan|report|session|...
captured_at: <ISO>
provenance: {repo, commit, path}
fragment_index: 0
parent_session_ref: "<agent>:<sid>"
```

### B. Knowledge slice（`knowledge/<project>/<slice_id>.md`)— union schema
```yaml
# — Stage 3 必填（過 lifecycle.schema）—
phase: research|define|plan|build|verify|review|ship
project: <project>
slice_id: sl-<sha256(project,agent,session,fragment_index)[:16]>
artifact_kind: <ARTIFACT_KINDS 之一>
version: "1"
created_at: <ISO>            # = captured_at
created_by: <agent>          # = source_agent
source_session: <sid>
gate_required: false
checksum: <sha256(body)>     # 必須 == compute_checksum(body)
# — T4 讀取契約（供 janitor）—
memory_layer: knowledge
source_agent: <agent>
captured_at: <ISO>
provenance: {repo, commit, path}
supersedes: []               # MVP 預設空（語意 supersede 留 T3.2）
# — 溯源 —
distilled_from: "<agent>:<sid>"
fragment_ref: "<agent>__<sid>__<NNN>"
```
映射表(確定性,放 config):

| source_artifact | artifact_kind | phase |
|---|---|---|
| research | research | research |
| plan(s) | plan | plan |
| spec | spec | define |
| report(s) | report | review |
| review | review | review |
| session(s) / 未知 | report(default) | review(default) |

> Stage 3 `ARTIFACT_KINDS` = research/spec/roadmap/test/task/todo/plan/report/review/ship-record/gate-report;`PHASES` = research/define/plan/build/verify/review/ship。

### C. `processing.jsonl`（狀態機,key = `<agent>:<session>`)
```json
{"ts":"<now>","session_key":"claude:sid","state":"split","fragments":3,"raw_archived_to":"archive/sessions/2026-05/claude__sid.md","atomizer_config_hash":"<h>"}
{"ts":"<now>","session_key":"claude:sid","state":"promoted","slices":3,"fragments_archived":3,"atomizer_config_hash":"<h>"}
```
- fold → 每 session_key 最新 state:`split` = **處理中(確定性已分析)**、`promoted` = **已處理(已原子化)**。
- **無 entry = 尚未處理(implicit `ingested`)**:T3 只寫 `split`/`promoted` 兩種 entry(T2 不碰此 ledger);「ingested」是隱含態,非實際 entry。

### D. `relations.jsonl`（派生邊,node 命名空間 `session:`/`fragment:`/`slice:`)
```json
{"ts":"<now>","type":"fragment_of","from":"fragment:claude__sid__000","to":"session:claude:sid","atomizer_config_hash":"<h>"}
{"ts":"<now>","type":"promoted_to","from":"fragment:claude__sid__000","to":"slice:sl-abc123"}
{"ts":"<now>","type":"distilled_from","from":"slice:sl-abc123","to":"session:claude:sid"}
{"ts":"<now>","type":"supersedes","from":"slice:sl-new","to":"slice:sl-old"}
```
確定性邊型別:`fragment_of` / `promoted_to` / `distilled_from` / `supersedes`。`neighbors(node)` 供 T7。

### E. `atomizer.yaml`（預設 + `~/.config/paulshaclaw/atomizer.override.yaml` 合併)
```yaml
schema_version: 1
split:
  boundaries: [turn, heading, artifact]
  max_fragment_chars: 8000
artifact_kind_map: { research: research, plan: plan, plans: plan, spec: spec,
                     report: report, reports: report, review: review,
                     session: report, sessions: report }
phase_map: { research: research, spec: define, plan: plan, report: review, review: review }
default_artifact_kind: report
default_phase: review
```
`atomizer_config_hash = sha256(canonical(effective))`。

### F. Archive 佈局
- 消耗的 raw session → `archive/sessions/<YYYY-MM>/<agent>__<sid>.md`
- 消耗的 fragments → `archive/fragments/<YYYY-MM>/<agent>__<sid>__<NNN>.md`

---

## 4. 資料流

`pipeline.run` = **兩個獨立、可重入的 pass**（crash 後下一輪自動接續）。

### Pass 1 — split_pass（raw → fragments）
work-list = raw 層(T2 輸出區)的 session 文件。每份:
```
1. 讀 + 解析 frontmatter
2. splitter.split(body) → list[Fragment]（確定性）
3. 原子寫 fragments → inbox/_slices/<project>/<agent>__<sid>__<NNN>.md
4. relations.append(fragment_of: fragment→session)
5. processing.append(state=split, fragments=N, now=<注入>)
6. 移動 raw session → archive/sessions/<YYYY-MM>/...   ← flow-through:raw 區清空
```
冪等:該 session_key 已 state≥split → 不重切;raw 仍在原區(crash 殘留)→ 補完步驟 6 搬移。

### Pass 2 — promote_pass（fragments → knowledge）
work-list = processing fold 中 state==`split` 的 session_key。每個其 fragments:
```
1. Promoter.promote(fragment) → list[Slice]   # MVP IdentityPromoter 1:1
2. slice_frontmatter:建 union frontmatter、算 slice_id/checksum、映射 artifact_kind/phase
3. 雙重驗證:lifecycle.schema.validate_frontmatter(Stage 3) + T4 契約檢查
   - 失敗 → 該 slice fail-closed(fragment 留著、warning),不寫 knowledge、不前進 promoted
4. 原子寫 knowledge slice → knowledge/<project>/<slice_id>.md
5. relations.append(promoted_to: fragment→slice;distilled_from: slice→session)
6. processing.append(state=promoted, slices=M, now=<注入>)
7. 移動 fragments → archive/fragments/<YYYY-MM>/...   ← flow-through:inbox/_slices 清空
```
冪等:state==promoted → 跳過;slice_id 由(session,fragment_index)決定 → 重跑 overwrite。

### 三個正確性保證
1. **冪等 / crash-resume**:兩 pass 各由「檔案 + processing 狀態」推導 work-list。步驟順序(先寫產物 → 再記 ledger → 最後搬移)確保任一中斷點重跑都安全。
2. **flow-through**:Pass 1 後 raw 區無已處理 session;Pass 2 後 inbox/_slices 無已升 fragment。
3. **決定性**:`now` 注入;fragment 順序、slice_id、checksum 全確定性;`atomizer_config_hash` 蓋章。

### 邊界處理
- **同 session 重匯入(內容變)**:raw 重現 raw 區 → 重跑,slice_id 不變 → overwrite knowledge slice。
- **relations 重複邊(crash 視窗)**:消費端(T7)以 `(type,from,to)` dedup。
- **空 split**:0 fragments → 仍記 processing(state=split, fragments=0),不產 slice。

---

## 5. 錯誤處理 & Guardrails

原則:**核心狀態出錯 → fail-closed;單筆/輔助出錯 → 降級續做**。

| 失敗 | 風險 | 處置 |
|---|---|---|
| `atomizer.yaml`/override 載入失敗、不支援 schema_version | 用未知設定 | **fail-closed**:中止、exit≠0、不寫 |
| `processing.jsonl`/`relations.jsonl` 壞行 | 核心狀態 | **fail-closed**:中止該 pass,WARN 標行號 |
| 單筆 raw session frontmatter 壞 / 缺 project·session | 局部 | **跳過 + WARN**,計入 `skipped` |
| **slice frontmatter 驗證失敗**(Stage 3 或 T4) | knowledge 落髒資料 | **該 slice fail-closed**:不寫、session 留 split、fragment 不 archive、WARN |
| 原子寫失敗 | 落盤不全 | **fail-closed** 該項,靠冪等重跑,exit≠0 |
| archive 搬移失敗 | flow-through 中斷 | 順序保證可恢復:重跑見 state=split + raw 仍在 → 補完搬移 |
| flock 競用 | 並發 | processing/relations 各自獨立鎖,逾時 WARN+exit≠0 |

WARN/error → `~/.agents/memory/log/atomizer.log`,不輸出記錄內文。

| # | Guardrail | 如何保證 |
|---|---|---|
| G1 | 不擴充 Stage 3 frontmatter schema | 只賦值並用 `lifecycle.schema.validate_frontmatter` 驗證;union 多出的是 T4(Stage 2 自有)欄位,Stage 3 驗證不拒絕額外欄位 |
| G2 | 不動 T2 importer | 只讀 raw 區、消耗時 move→archive |
| G3 | flow-through 不毀證據 | 消耗輸入 move 到 archive(非刪) |
| G4 | knowledge 只放有 provenance/可引用結論 | 每 slice 必帶 provenance + checksum + distilled_from,驗證強制 |
| G5 | ledger append-only 不改寫 | processing/relations 只 append |
| G6 | 決定性 | `now` 注入、MVP 無 LLM/隨機、`atomizer_config_hash` 可追溯 |
| G7 | 記錄在冊 | 每處理過 session 必有 processing(split/promoted)+ relations 邊;slice `distilled_from` 標明出處 |

> slice 驗證失敗會讓 session **卡在 `split`**(每輪重試同樣失敗,確定性)——刻意暴露問題,非無限迴圈;修 config/mapping 後自動解。

---

## 6. 測試策略（TDD,fixture E2E 為主目標）

`now`/`ts` 全注入,場景可復現。

### 單元測試
| 測試檔 | 覆蓋 |
|---|---|
| `test_atomizer_splitter.py` | turn/heading/artifact 邊界、優先序、`max_fragment_chars` 再切、空 session→0、fragment_index、決定性 |
| `test_slice_frontmatter.py` | union 齊全、slice_id 決定性、checksum==sha256(body)、artifact_kind/phase 映射(含 default)、過 Stage3 + T4 驗證、缺欄位→errors |
| `test_atomizer_promoter.py` | IdentityPromoter 1:1、slice 帶 distilled_from/fragment_ref |
| `test_ledger_processing.py` | append/read/fold、split/promoted 查詢、flock、壞行 fail-closed、ts 注入 |
| `test_ledger_relations.py` | append/read、`neighbors()`、`(type,from,to)` dedup、flock、壞行 fail-closed、ts 注入 |
| `test_atomizer_config.py` | 預設/override 合併、hash 決定性、不支援 schema_version fail-closed |

### E2E（`test_atomizer_e2e.py`,臨時 memory root + fixture raw session）
| 場景 | 斷言 |
|---|---|
| A split_pass | fragments 落 inbox/_slices、raw 移 archive、state=split、fragment_of 邊 |
| B promote_pass | knowledge slices 寫出(過 Stage3+T4)、fragments archived、state=promoted、promoted_to/distilled_from 邊 |
| C 全跑 1:1 | slice 數 == fragment 數 |
| D 冪等重跑 | 第二次 0 新產出 |
| E crash-resume | state=split + fragments 在、raw archived → 跑 → promote 補完 |
| F flow-through | 全跑後 raw 區空 + inbox/_slices 空;archive 兩者都有 |
| G 重匯入更新 | raw 換內容 → 重跑 → 同 slice_id overwrite、checksum 變 |
| H 驗證 fail-closed | 無法映射成合規 artifact_kind 的 fragment → 不寫、state 留 split、warning |
| I dry-run | 零寫入/零搬移,回 plan/summary |
| 跨 stage 契約 | 產出 slice 餵 `python3 -m paulshaclaw.lifecycle.gate` 驗證通過 |
| 安全 | ledger 內無 raw 記錄內文 |

### Fixtures & 整合
- `paulshaclaw/memory/tests/fixtures/atomizer/raw/<...>.md` — 符合 importer 輸出 frontmatter、body 含結構邊界。
- 擴充 `stage2_integration_check.sh`:加 atomizer dry-run over fixtures。
- 回歸:`unittest discover -s paulshaclaw/memory/tests` 與 `tests/` 全綠。

---

## 7. 解鎖的後續（非本 change 範圍）
- **T3.2（語意 atomizer)**:把 `Promoter` 換成 LLM 實作(語意拆分/合併 + 語意 relations + tag);splitter/ledger/frontmatter/flow-through 全複用。
- **T7（Retrieval)**:消費 `relations.jsonl`(relation traversal）+ knowledge slices(lexical 索引)+ T4 `active_records()`(可見集)。
