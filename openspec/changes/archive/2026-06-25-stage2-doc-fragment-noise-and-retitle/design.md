## Context

延續 #139 P2（#144/#145）。清掉 importer 結構 echo 後，paulshaclaw wake-up brief 仍被兩類問題洗版：(1) instruction 文件碎片（#147，全店 102 編號段落 + 24 untitled-AGENTS），(2) untitled 真知識（#151，~15 個）。兩者共用 `classify_noise` 與 MOC 命名管線，故合併處理：先以 doc-fragment 規則刪碎片，再對剩餘 untitled 真知識重生標題。

## Goals / Non-Goals

**Goals:**
- doc-fragment 以 corpus 逐字比對判定（deletion-grade，只刪可證實的 instruction 逐字片段）。
- 產生端與回溯 prune 共用同一判準與語料。
- `slugify` 保留 CJK，使重生的中文標題產生可讀檔名/wikilink target。
- retitle 重生標題並改名，保留 slice_id 與 body，不誤動。

**Non-Goals:**
- splitter/import 端跳過 instruction-doc session（#147 方向 B，視效果再評估）。
- 既有非 untitled slice 的標題品質調校。
- promoter prompt 調校。

## Decisions

- **doc-fragment 判準（A：corpus 逐字比對）**：否決純結構啟發式（`## N.` heading + 指令標記）——對 instruction 文件無標記的短段落（1-5 章節）易漏判、對真有編號小節的知識易誤判。corpus 逐字比對只在「heading 與 ≥2 內容行皆逐字命中 instruction 語料」時判 noise，誤刪面最小。
- **語料為選用參數**：`classify_noise(fm, body, *, doc_corpus=None)`，None/空語料時 doc-fragment 規則惰性 → 既有測試與行為零變更。語料 IO 與探測落在 `instruction_corpus`（CLI/產生端組裝），`noise.py` 保持純函式 + `DocCorpus` 型別。
- **語料探測邊界化**：curated roots（`~/.claude`、`~`、`~/.codex`、`~/.agents`、`~/.gemini`、`~/prj_pri`、`~/prj_ext`、repo 自身），os.walk 限深 + skip-list（`.git`/`node_modules`/`archive`/`knowledge`/`.copilot`…）。避開記憶教訓中 `~/.copilot`（3.3GB）無邊界掃描 OOM。
- **slugify 保留 CJK（根因修法）**：`[^a-z0-9]+` → `[^\w]+`（re.UNICODE，含 CJK 文字與數字）。純標點/空字串仍 fallback `untitled`。零既有 churn（驗證現存 slice `title:` 欄位皆 ASCII，故 reconcile 不重命名既有檔）。
- **retitle 走獨立一次性 migration**（非 atomize；`_split_pass` 對 promoted session 冪等 skip）。候選＝`title==untitled` 或 `untitled--` 檔名、且非 doc-fragment（雙重防護，避免 retitle 應刪的碎片）。gemma4 body 蒸餾，runner 可注入（測試不依賴線上 LLM）；離線 slice skip 記 manifest，migration 不失敗。
- **改名保留 slice_id**：以 `naming.slugify(title)` 算新檔名 `<slug>--<slice_id>.md`，slice_id 不變；MOC/relations 以 slice_id 索引，rename 安全。stamp `title`/`atom_title`/`aliases`。**不**動 `session_title`：MOC leaf label 取 `atom_title or session_title or basename`，stamp `atom_title` 已修好 brief 可見的 leaf 標題；`session_title` 只餵 parent spine 分組，且現存 untitled slice 的 `session_title` 多為真值（如「修正 start.sh…」），無需改寫。rename 目標已被占用（重複 slice_id）時只 stamp 不改名、manifest 記 `stamped`，交由 `run_moc`/`reconcile` 以 mtime 收斂。

## Risks / Trade-offs

- **誤刪風險（#147）**：corpus 逐字比對 + `--dry-run` 預設 + manifest 人工關卡。instruction 文件演進（舊 session 內容對不上現行 doc）僅造成「漏刪」（安全側），不會誤刪真知識。apply 前人工核 manifest。
- **hard delete 不可逆**：source session 在 archive 為真相源；live store 為 git work-tree 可回復；`--apply` 顯式觸發。
- **CJK 檔名**：Linux/UTF-8 與 Obsidian wikilink 皆支援；既有 ASCII slug 不受影響。
- **gemma4 依賴（#151）**：離線無法重生 → 對應 slice skip，待上線重跑；不阻斷 #147 prune。
- **語料缺漏**：探測不到某 instruction doc 時該類碎片漏刪（安全側），可補 `--instruction-root` 指定。
