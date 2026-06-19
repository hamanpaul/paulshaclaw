# Stage 2 — Topic 7：paulsha-mem-moc（Obsidian-native MOC / 鏈結 + lexical search）設計

- 日期：2026-06-03
- 範圍：T7 = `paulsha-mem-moc`（dream 核心整理者）。把 `knowledge/` 補成 Obsidian-native vault：materialize 關聯、可讀檔名、三類 MOC、faceout、lexical search。
- 命名：`paulsha-memory` = Stage 2 整體（`~/.agents/memory` 維護者）；**`paulsha-mem-moc` = dream mode 核心整理者（本 change）**。
- 前置：T3/T3.2（knowledge slices + `relations.jsonl`）、T4（active-set / lifecycle）、T5（dream orchestrator）皆已完成。
- 依據（原意）：`docs/research/00`（MOC 結構 + Obsidian 關聯 + faceout）、`openspec/specs/stage0-tooling/spec.md`（`obs-auto-moc → paulsha-memory` rename matrix）；`custom-claw-tools/obs-auto-moc` 僅參考、自建、不耦合。

---

## 0. 與 T3/T5 的衝突解法（headline）

| # | 衝突 | 解法 |
|---|---|---|
| C2 | wikilink 放 body 會破壞 Stage 3 `checksum=sha256(body)` 與 T3.2 內容派生 `slice_id` | **鏈結只放 `related:` frontmatter,絕不進 body**（Obsidian 認 frontmatter `[[..]]`）|
| C1 | atomize 寫死 `knowledge/<project>/<slice_id>.md`；改名後 reimport 產重複 slice_id（selector 遇重複 raise）| 檔名 `<title>--<slice_id>.md`；**atomize 改用 `*--<slice_id>.md` glob 定位覆寫** |
| C4 | MOC 檔（無 slice_id）被 janitor/selector 當 slice 掃 | MOC 帶 `memory_layer: moc`；**janitor record_source + selector 明確排除** |
| C3 | atomize 覆寫 slice 會清掉 moc 的 `related:` | moc pass **永遠在 atomize 之後**跑（dream: atomize→janitor→**moc**），每輪冪等重建 |

**必要連動修改：** T3.2 `atomizer/pipeline.py`（C1）；T4 `janitor/record_source.py` + T5 `replay/selector.py`（C4）；T5 `dream/orchestrator.py`+`cli.py`（加 moc pass）。

---

## 1. 範圍與邊界

### In scope（A–E + faceout，純確定性、無 LLM）
- **A** materialize `relations.jsonl` → slice 的 `related:` frontmatter（雙向 `[[..]]`）。
- **B** 可讀檔名 `<title>--<slice_id>.md`（slice_id 留 frontmatter 當穩定鍵）。
- **C** 三類 MOC：`<project>-moc.md` / `common-sense-moc.md` / `wiki-moc.md`（帶 `memory_layer: moc`）。
- **D** vault 邊界 = `knowledge/`（其餘 runtime/archive/inbox 不入 vault）。
- **E** lexical search：FTS5 sidecar（`runtime/indexes/retrieval.db`），`psc memory search`。
- **faceout**：T4 decayed slice 在 `wiki-moc.md` mark faceout。
- 在 **dream pass**（atomize→janitor→**moc**）冪等重建。

### Out of scope（明確劃走）
- ❌ 語意理解 / LLM（T7 純確定性）。**跨 session 實體正規化/聚合（curated entity graph）= T5-C**；演進脈絡 = T5-B；SkillOpt = evolve follow-up。
- ❌ 鏈結進 body；改 ledger（relations.jsonl 仍是 append-only 真實來源,只 materialize）。
- ❌ 耦合 / 使用 obs-auto-moc（僅參考、自建）。

### 邊界與既有 LLM 工作的分界
- T3.2 = 語意**產生** relations（LLM,per-session）→ relations.jsonl。
- **T7 = 確定性 materialize**：把 mentions/relates_to 翻成 `[[..]]`，實體圖**在 Obsidian 自然浮現**（T7 不建 curated 實體圖）。

---

## 2. 架構與元件

```
paulshaclaw/memory/moc/                  # = paulsha-mem-moc
├── linker.py        # relations.jsonl → 每 slice 的 related: frontmatter（雙向，不碰 body）
├── naming.py        # title → <title>--<slice_id>.md;rename 對帳 / 去重
├── moc_builder.py   # <project>-moc.md / common-sense-moc.md / wiki-moc.md（memory_layer: moc）
├── faceout.py       # decayed slice → wiki-moc.md mark faceout
├── search.py        # FTS5 build + query
├── runner.py        # moc pass:link → rename → moc → faceout → index（冪等重建）
└── cli.py           # psc memory search
```
連動修改：`atomizer/pipeline.py`（C1）、`janitor/record_source.py`、`replay/selector.py`（C4）、`dream/{orchestrator,cli}.py`（加 moc pass）。

| 元件 | 職責 | 依賴 | 介面 |
|---|---|---|---|
| `moc/naming.py` | title 推導 + 目標檔名 + rename 去重 | frontmatter | `target_name(slice)` / `reconcile(memory_root)` |
| `moc/linker.py` | 雙向 related 集 → frontmatter；算 link_weight | relations.neighbors | `materialize_links(memory_root)` |
| `moc/moc_builder.py` | 三類 MOC | knowledge fs、retrieval_set | `build_mocs(memory_root, now)` |
| `moc/faceout.py` | decayed → wiki-moc | lifecycle/retrieval_set | `mark_faceout(memory_root)` |
| `moc/search.py` | FTS5 索引 + 查詢 | sqlite3 | `build_index(memory_root)` / `search(memory_root, q, ...)` |
| `moc/runner.py` | 一輪 moc pass | 上列全部 | `run_moc(memory_root, now)->dict` |

決定性：moc pass 純讀檔+ledger、決定性重寫；`now` 注入；冪等完整重建。

---

## 3. 資料模型

### A. Slice frontmatter 新增（只動 frontmatter）
```yaml
title: <可讀標題>
aliases: ["<title>"]
related:
  - "[[<title>--<slice_id>]]"   # relates_to slice 鄰居
  - "[[MTK]]"                   # mentions entity（未解析也在 graph 出現）
```
`distilled_from` 維持原樣；entity 節點即使無對應 note,graph 也顯示 → 實體圖自然浮現。

### B. 三類 MOC（`knowledge/`,帶 `memory_layer: moc`）
```yaml
# <project>-moc.md   → moc_kind: project, project: <p>
# common-sense-moc.md → moc_kind: common-sense（project == "common-sense"）
# wiki-moc.md         → moc_kind: wiki（全索引）
```
`wiki-moc.md`：
```markdown
## Active
- [[<title>--<slice_id>]] — <project> · <artifact_kind>
## Faceout
- [[..]] — decayed: <reason>, since <ts>
```

### C. FTS5 索引（`runtime/indexes/retrieval.db`,每輪完整重建）
```sql
CREATE VIRTUAL TABLE slices_fts USING fts5(slice_id UNINDEXED, project, title, tags, body, tokenize='unicode61');
CREATE TABLE slice_meta (slice_id TEXT PRIMARY KEY, project TEXT, captured_at TEXT,
                         active INTEGER, link_weight INTEGER);  -- link_weight=related 數
```
`search(q, project=, limit=, include_decayed=)`：FTS5 MATCH→bm25;join slice_meta 過濾 project/active + 取 recency/link_weight → **rank = w1·bm25 + w2·recency + w3·link_weight** → 回 `[{slice_id, title, project, score, snippet}]`。

### D. Faceout
decayed slice → 列 `wiki-moc.md ## Faceout`（reason + since）；**不改 slice frontmatter、不刪檔**（lifecycle ledger 為真實來源）。

---

## 4. 資料流

### moc pass `run_moc(memory_root, now)`（atomize→janitor 之後）
```
1. naming.reconcile：掃 knowledge/**/*.md（排除 memory_layer:moc）;每 slice → <slug>--<slice_id>.md;
   名不符則 rename;以 frontmatter slice_id 去重（一個 slice_id 一檔）
2. linker.materialize_links：建圖,每 slice 寫 related:（relates_to 雙向 + mentions entity）+ title/aliases;
   只動 frontmatter（body/checksum/slice_id 不變）;算 link_weight
3. moc_builder.build_mocs：active = retrieval_set.active_records;分組產三類 MOC
4. faceout.mark_faceout：decayed → wiki-moc ## Faceout
5. search.build_index：完整重建 FTS5
→ 回 {renamed, linked, mocs, faceout, indexed}
```

### atomize 連動（C1）
寫檔改:glob `*--<slice_id>.md` 定位 → 存在則覆寫,否則寫 `<slice_id>.md`（首次,moc 後改名）。reimport 不產重複。

### dream 接點
orchestrator:`atomize_fn → janitor_fn → moc_fn`。moc 為**第三個隔離 pass**（失敗記錄不阻斷;讀既有 knowledge,前兩 pass 失敗仍可跑）。dream.jsonl `passes` 增 `moc`。

### search 查詢流（`psc memory search "<q>" [--project --limit --include-decayed]`）
開 retrieval.db（缺→報錯）→ FTS5 MATCH → join slice_meta 過濾 → rank → limit → JSON。唯讀。

### 決定性 / 冪等
moc pass 完整重建冪等;rename target 穩定;frontmatter 原子寫;MOC/index 全覆寫。`now` 注入。

---

## 5. 錯誤處理 & Guardrails

moc 是 dream 隔離 pass;**五步各自最佳努力,核心狀態壞才 fail-closed 該步,整 pass 不 crash dream**。

| 失敗 | 處置 |
|---|---|
| `relations.jsonl` 壞行 | linker 該步 fail-closed（related 維持上次）+ warn;其餘步驟照跑 |
| 單 slice frontmatter 壞 / 缺 slice_id | 跳過 + warn |
| 重複 slice_id | naming 去重 + warn |
| frontmatter/MOC/index 寫入失敗 | 該項 fail + warn;原子寫;冪等重跑修復 |
| FTS5 不可用 / index 缺壞 | search build 跳過 + log,不 crash;query 回「先跑 dream」 |
| MOC 被當 slice 掃 | memory_layer:moc 排除（test 守）;漏則 janitor 只 warn |

log → `~/.agents/memory/log/moc.log`,不含 raw。

| # | Guardrail | 保證 |
|---|---|---|
| G1 | 鏈結絕不進 body | 只寫 frontmatter → checksum + slice_id 不變 |
| G2 | slice_id 穩定身份,檔名衍生 | rename 不改 slice_id |
| G3 | MOC 排除於知識掃描器 | memory_layer:moc;janitor/selector 跳過 |
| G4 | relations.jsonl 仍 append-only 真實來源 | moc 只讀+materialize,不寫 relations.jsonl |
| G5 | moc pass 冪等完整重建 + 隔離 | 重跑同輸出;不阻斷 atomize/janitor |
| G6 | vault 邊界 | 只動 knowledge/ |
| G7 | faceout 不刪 | decayed 留 knowledge/（T4 管生命週期）|
| G8 | 決定性 / 無 raw | now 注入;knowledge 已 redacted |
| G9 | 不耦合 obs-auto-moc | 自建,僅參考 |

---

## 6. 測試策略（TDD,純確定性）

### 單元
| 測試檔 | 覆蓋 |
|---|---|
| `test_moc_naming.py` | slugify、target 檔名、rename 對帳、重複 slice_id 去重、缺 title fallback |
| `test_moc_linker.py` | related: 由 relates_to+mentions、**只進 frontmatter body 不變 checksum 不變**、link_weight、title/aliases |
| `test_moc_builder.py` | 三 MOC 帶 memory_layer:moc、project 分組、common-sense、wiki ## Active |
| `test_moc_faceout.py` | decayed→wiki-moc faceout、不刪、active 不入 |
| `test_moc_search.py` | FTS5 build+query、bm25、project/active 過濾、include-decayed、link_weight/recency 加權、缺 index 報錯 |
| `test_moc_runner.py` | 五步順序、冪等、步驟隔離 |

### 衝突回歸
| 測試 | 斷言 |
|---|---|
| C2 | materialize 後 slice 仍過 Stage3 validate、slice_id 不變 |
| C1 | 改名後 atomize reimport → 覆寫該檔、無重複 slice_id |
| C4 | janitor record_source + selector 跳過 memory_layer:moc |
| C3 | dream atomize→janitor→moc related: 存在、重跑一致 |

### 連動修改
atomizer glob 覆寫；janitor record_source / selector 排除 memory_layer:moc。

### E2E / 整合
- `test_moc_e2e.py`（經 dream）：改名 slice + related: + 三 MOC + wiki-moc；search 撈到；bundle 仍正常（排除 MOC）；slice 過 `lifecycle.gate`。
- Obsidian-vault sanity：body 無 `[[..]]`、MOC 帶 memory_layer:moc、related 解析到既有 basename。
- `stage2_integration_check.sh` 加 dream（含 moc）+ `psc memory search` + 斷言 MOC/related/hit。
- 回歸：memory 套件 + `tests/` 全綠；**T3.2/T4/T5 在連動修改後仍綠**。

---

## 7. 解鎖的後續（非本 change）
- **T5-C 全域實體圖**（LLM）：跨 session 實體正規化/聚合（MTK/MediaTek 合一、curated 實體索引）。
- **T5-B 演進脈絡**（LLM）：跨 session supersede/演進鏈。
- **T6 wake-up**：消費 MOC + search + dream status 組晨間 bundle。
- Obsidian 端：使用者用 graph view / Dataview / 自己的 vault 流程消費 knowledge/ vault。
