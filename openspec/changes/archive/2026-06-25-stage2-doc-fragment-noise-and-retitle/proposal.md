## Why

#139 P2（#144/#145）清掉 importer 結構 echo 後，agent wake-up brief 仍有**第二類噪音**與**標題缺失**兩個問題：

- **#147 doc-fragment 碎片**：CLAUDE.md / AGENTS.md 等 agent-instruction 文件被 splitter 依 `## N.` heading 切片、各自原子化成 knowledge slice。全店 102 個編號段落（`1--`/`2--`…/`6-agent-managed--`，皆為本 repo CLAUDE.md 的 6 個 `## N.` 章節 × 17 session）＋約 24 個 `untitled--`（body 為 AGENTS.md 段落）。冗餘（instruction 每 session 已載入）、碎片化、洗版 brief（占清理後 ~35%）。現有 classifier 以 importer 結構 heading 判 echo，**抓不到 `## N. <中文標題>` 這類 doc 碎片**。
- **#151 untitled-- 真知識**：title 生成當時 gemma4 離線 → `title: untitled` → 檔名 slug `untitled--`，注入給 agent 的 raw brief 看得到。根因是 `slugify()` 把純 CJK 標題 strip 成空字串 → fallback `untitled`。扣掉 #147 會清掉的 24 個 doc 碎片，剩約 15 個是真知識，需重生標題並改名。

## What Changes

- **doc-fragment classifier（#147）**：`classify_noise` 新增 `doc-fragment` 類別——以 CLAUDE.md/AGENTS.md/GEMINI.md 為**逐字參照語料**（corpus），body 第一行 heading 命中語料 heading 且 ≥2 內容行逐字命中語料行者判為 noise。deletion-grade：只刪「可證實是 instruction 文件逐字片段」者。語料為選用參數，未提供時規則惰性（向後相容）。
- **corpus 探測（#147）**：新增 `instruction_corpus` 模組，自安全的 instruction-doc 位置（curated roots，避開 `~/.copilot` 等重目錄）探測並建語料；prune CLI 與產生端共用。
- **產生端過濾（#147）**：atomize promote pass 套用 doc-fragment 規則（傳入語料），阻斷新生。
- **回溯 prune（#147）**：`prune-noise` 套 doc-fragment 規則回溯清既有碎片，輸出稽核 manifest。
- **slugify 保留 CJK（#151）**：`slugify()` 改保留 Unicode 文字（含 CJK），純 CJK 標題不再塌成 `untitled`。零既有 churn（現存 slice 的 `title:` 欄位皆 ASCII）。
- **retitle migration（#151）**：新增 `psc memory knowledge retitle-untitled`——對 `title=untitled`（或 `untitled--` 檔名）且非 doc-fragment 的真知識 slice，用 gemma4 對 body 蒸餾 ≤20 字 zh-TW 標題、stamp `title`/`atom_title`/`aliases`、**重命名檔案保留 slice_id**、重建 MOC。gemma4 離線者 skip 並記 manifest。

## Capabilities

### Modified Capabilities
- `stage2-noise-governance`: classifier 新增 `doc-fragment`（corpus 逐字比對）類別，產生端與 prune 共用語料。

### New Capabilities
- `stage2-knowledge-retitle`: untitled 真知識 slice 的標題重生（gemma4 body 蒸餾）、檔名重命名（保留 slice_id）與稽核 manifest；`slugify` 保留 CJK。

## Impact

- 程式：新增 `paulshaclaw/memory/instruction_corpus.py`；改 `paulshaclaw/memory/noise.py`（加 `DocCorpus`/`build_corpus`/doc-fragment 規則）、`paulshaclaw/memory/moc/naming.py::slugify`、`paulshaclaw/memory/atomizer/pipeline.py::_promote_pass`、`paulshaclaw/memory/cli.py`（加 `knowledge retitle-untitled`、prune 接語料）；新增 `paulshaclaw/memory/retitle.py`。
- 資料：live store `knowledge/**.md` 既有 ~126 doc 碎片將 hard delete（manifest `runtime/ledger/prune-<ts>.jsonl`）；~15 個 untitled 真知識重命名 + stamp 標題（manifest `runtime/ledger/retitle-<ts>.jsonl`）；raw archive 不動；live store 為 git work-tree（可回復）。
- 部署：dream loop 下個 tick 自動用新碼；回溯清理與 retitle 為一次性人工 `--apply`（gemma4 須上線）。
