# Memory 消費迴路（task-conditioned 檢索 → native Read 遞送 → read-based 歸因）設計

> 日期：2026-06-29 ｜ 來源：brainstorming（合併修復 fix 1-3）
> 前置：Stage 2 執行情況評估 + 6 agent workflow root-cause 分析發現 `memory_usage.jsonl` 6 筆全 `cited:[]/matched:[]`。
> 關係：**取代** #148（usage telemetry）的 SessionEnd 逐字偵測主訊號；**延伸** #144/#147/#151/#153 噪音治理到 `agents-md-fragment`/空 session 類；建立於 #150 readback brief 之上（但 SessionStart brief 改瘦身）。

## 1. 背景與問題（root-cause 摘要）

`0/6` 引用是**過度決定（overdetermined）**的，按貢獻排序：

1. **內文從未遞送（最上游）**：`build_brief` 只給 MOC 標題索引 + 8 條一行摘要，slice 內文從不進 context，連結是 `[[stem]]` 在 Claude Code（非 Obsidian）無法 dereference。agent 拿到的是「打不開的指標」。
2. **量測不到**：`extract_cited` 要 agent 逐字回吐 16-hex id、`extract_matched` 要標題逐字命中；皆非自然行為，且 47% offered 標題是佔位 `# AGENTS.md instruct`、~17% 是被砍斷的中文。`0/0` 是儀器地板。
3. **任務盲檢索**：brief 在 SessionStart、prompt 之前建構，只吃 `project+時間`；真正的 bm25 ranker（`search.py`）只接到手動 CLI。相關性靠巧合。
4. **池子噪音**：229 筆 live knowledge 中 127 筆（55%）是 `# AGENTS.md instruct` 片段（已逐字在 system prompt 內，永不需引用）；actionable 僅 ~22%。

**本設計把死迴路換成活迴路**：任務條件式檢索 → 短清單推送（含可開啟的絕對路徑）→ agent native Read 拉全文 → 讀取即歸因；並從生產端與池端掐掉噪音、瘦身 SessionStart brief。

## 2. 決策（brainstorming 拍板）

| 決策 | 選擇 | 理由 |
|---|---|---|
| Win condition | **消費優先**：記憶真的改變 agent 行為；遙測只是佐證 | 量測是手段不是目的；先讓相關內文確實送達並被用到。 |
| 遞送 ⊕ 歸因 | **Hybrid**：UserPromptSubmit 推短清單（標題·一行·絕對路徑）→ agent 對相關項拉全文 | 推保證「相關內文進得了 context」、拉保證「精準歸因」、token 可控。 |
| 拉取管道 | **native Read + PostToolUse hook 歸因** | 對 agent 零新概念、最低摩擦；歸因精準但限有 PostToolUse 的 Claude Code，codex/copilot 退化為缺測（已接受）。 |
| 噪音清理 | **最乾淨**：生產端過濾 + 池端過濾 + 刪除現存噪音（prune dry-run gated） | 一次把產生端、消費端、存量都治掉。 |
| 短清單 k | **3**（上限 5） | 高精度短清單比長 dump 更可能被拉。 |
| relevance gate | FTS5 有命中 + top 結果過門檻才推 | 避免 trivial prompt（`/effort`、「謝謝」）灌清單。 |
| 推送頻率 | **每個過 gate 的 prompt 都推**（非僅首輪） | 接得住 session 中途換題。 |
| canary/review 類 | **只池端排除、不刪檔**；刪除只動 `agents-md-fragment` + 空 `session-metadata` | 刪除限「結構性非知識且確定冗餘」者，降低誤刪。 |
| SessionEnd 舊偵測器 | **退役主訊號**（保留 offered 記錄、不再用逐字 cited/matched） | 假 0 來源；read-based 取代。 |
| SessionStart brief | **瘦成極簡 orientation**，不再倒 project MOC、移除 16-hex `CITATION_PREAMBLE` | 已被 prompt-time 檢索取代，且自身是噪音源。 |

## 3. 目標與非目標

**目標**
- UserPromptSubmit 時依當前 prompt 做 bm25 檢索，注入 top-k 短清單（含絕對路徑）。
- agent native Read 被推路徑時，PostToolUse 記精準 `used` 事件。
- 生產端不再把指令檔（CLAUDE.md/AGENTS.md/GEMINI.md）與空 session payload atomize 成 knowledge。
- 池端（index / brief）不再露出噪音類。
- 刪除現存 `agents-md-fragment` + 空 `session-metadata` 噪音（dry-run gated）。
- `psc memory usage` 改讀 read-based used 事件。

**非目標**
- codex/copilot 的 read 歸因（先 Claude-only；二者仍收短清單可 Read，但 used 缺測）。
- 取代既有 hourly dream / atomize / janitor / MOC 主流程（只增掛 hook 與過濾）。
- 強制 agent 一定要 Read（仍是建議；消費依賴短清單精度 + 提示，見風險 A3）。
- relevance 排序回授 decay（後續另案，需先有 read 數據）。

## 4. 架構與單元

### ① prompt-time 檢索（`hooks/claude_user_prompt_submit.py` + 共用 `hooks/_shortlist_common.py`）

UserPromptSubmit payload → `prompt`、`cwd`、`session_id`。

```
project = resolve_project(cwd)                 # _unknown → 不注入
fts_query = to_fts_query(prompt)               # 抽 alnum/CJK token，OR 連接，避免 FTS5 語法錯誤
hits = search.search(memory_root, fts_query, project=project, limit=k, include_decayed=False)
hits = [h for h in hits if passes_gate(h)]     # gate：有命中 + score 過門檻
if not hits: emit nothing                      # 不注入、不阻斷
for h in hits:
    path = abs_path_of(h.slice_id)             # <memory_root>/knowledge/<project>/<stem>.md
    summary = first_meaningful_line(path)       # 重用 builder 摘要邏輯
    line = f"- [{h.title}] — {summary} — {path}"
inject additionalContext(shortlist + 提示「相關項用 Read 開啟路徑取全文」)
append_offered(session_id, [(sl_id, path), ...])
```

- **offered 記錄**：append `runtime/ledger/offered.jsonl`：`{ts, session_id, tool, project, prompt_hash, offered:[{sl_id, path}]}`；並維護 per-session 累積映射 `runtime/wakeup/<tool>__<sid>.offered.json`（sl_id→path，跨本 session 多次 prompt 累積），供 PostToolUse 對齊。
- best-effort：index 缺 / `_unknown` / 無命中 / 任何例外 → 不注入、log、exit 0。

### ② read-based 歸因（`hooks/claude_post_tool_use.py`，settings 註冊 `matcher:"Read"`）

PostToolUse payload → `tool_name`、`tool_input.file_path`、`session_id`、`cwd`。

```
if tool_name != "Read": return
p = realpath(file_path)
if not under(p, memory_root/"knowledge"): return
offered = load_offered(session_id)             # runtime/wakeup/<tool>__<sid>.offered.json
sl_id = offered.path_to_id.get(p)              # 在 offered → offered=True；否則 offered=False（自行找到）
append used event → runtime/ledger/memory_usage.jsonl:
  {ts, session_id, tool, project, sl_id, path, source:"read", offered: bool}
```

- best-effort，永不破壞 Read 本身。

### ③ 生產端噪音過濾（擴 `noise.py` + atomizer/promoter pipeline）

- **分類（classification）** 涵蓋四類（供③丟棄與④排除共用單一真相源；`canary-fixture`/`review-record` 可能已部分由 #144/#147 既有 classifier 認得，缺者於此補上）：
  - `agents-md-fragment`：source 為專案 `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`（依 importer 的來源路徑/`distilled_from` 判定，非僅標題字串）。
  - `session-metadata-empty`：payload 無實質內容（如「the actual content of the payload was not present」）。
  - `canary-fixture`：canary/smoke 測試夾具（如 builder v2.0.0、canary-claude task）。
  - `review-record`：一次性 PR/adversarial review 記錄。
- **動作分流**：atomize → promote 前 **丟棄** `agents-md-fragment` + `session-metadata-empty` 兩類（不進 knowledge）；`canary-fixture`/`review-record` **不丟、僅由④池端排除**。沿用 #144/#147 既有 classifier 與 prune ledger 機制。

### ④ 池端過濾（`build_index` + slim brief）

- `build_index`（`search.py`）建 `retrieval.db` 時 **排除** 噪音類（`agents-md-fragment`/`session-metadata-empty`/`canary-fixture`/`review-record`）→ 短清單檢索自動乾淨。
- slim SessionStart brief（見⑥）讀 knowledge 時套同一排除集。
- 注意：canary/review 類 **只在此排除、不在③刪檔**。

### ⑤ 現存噪音 prune（既有 prune CLI，destructive、gated）

- `memory prune --classes agents-md-fragment,session-metadata-empty --dry-run` → 產 manifest（count + sample）。
- **先備份** `knowledge/`（`~/.agents` 非 git 追蹤，刪除不可 git undo）→ 人工核 manifest（數字超預估就停下問）→ `--apply` 刪 live。
- 此為 plan 內獨立 task，需人按手，不自動跑。

### ⑥ SessionStart brief 瘦身（`_wakeup_common.py` / `builder.py`）

- 由 40–78 筆 Map+Recent dump → 極簡 orientation：
  > 「記憶系統已啟用（本專案 N 筆 knowledge）。與當前任務相關的記憶會在每次 prompt 後以短清單浮現；用 Read 開啟列出的絕對路徑即取全文。」
- 移除過時 `CITATION_PREAMBLE`（16-hex 請求）。
- SessionStart 不再寫大 offered 集（offered 改由①per-prompt 記）。

### ⑦ 遙測整併（`usage_ledger.py` / `usage.py` / CLI）

- 主 `used` 訊號 = ②read 事件。
- 退役 SessionEnd `extract_cited`/`extract_matched` 主訊號（假 0 來源）；`usage.py` 保留 `extract_offered`/`to_fts_query` 等純函式。
- `psc memory usage` 改讀 read-based used：per-slice `offered_count / read_count / last_read`、never-read（offered 但未 read）。
- no-op/短 session：無 prompt → 無 offered → 無 used row，自然消除 #1/#2 假 0 記錄問題。

## 5. 資料流

```
UserPromptSubmit ─prompt+cwd─▶ ① bm25(project,prompt)→top-k(gate)
        │  inject 短清單[title·1-liner·/abs/path]
        └─ append offered(session→{sl_id,path})
agent ──native Read(/abs/path)──▶ 消費
        └─ ② PostToolUse(Read)：path∈knowledge ∧ ∈offered → append used  ← 精準歸因
dream(每小時)：③生產端過濾丟棄指令檔/空 payload；④build_index 排除噪音類；rebuild retrieval.db
operator(一次性,gated)：⑤prune dry-run→備份→核 manifest→刪現存噪音
SessionStart：⑥極簡 orientation（不再 dump）
CLI：⑦memory usage→read-based 聚合
```

**關鍵不變式**：offered 與 used 以 `session_id + 絕對路徑` 對齊（path 為唯一鍵，PostToolUse 才能對回是哪條被推送的記憶）。

## 6. 錯誤處理 / 韌性

- 所有 hook best-effort、exit 0、例外寫 `log/hooks.log`（沿用 #141 pattern），不阻斷 prompt/tool。
- ①：`to_fts_query` 對畸形/空 prompt 回空 → 不注入；index 缺 → 不注入。
- ②：path 不在 knowledge / offered 缺檔 / 解析失敗 → 靜默跳過。
- ⑤：刪前強制備份；dry-run 為預設，`--apply` 需顯式。

## 7. 測試（TDD）

- **單元**：`to_fts_query`（alnum/CJK 抽詞、特殊字元不致 FTS5 error）；`passes_gate` 門檻；offered 寫入/累積映射；②path-under-knowledge ∧ in-offered 判定（含 offered=False 分支）；③noise classifier 新類（指令檔 source / 空 payload）；④build_index 排除噪音。
- **e2e**：模擬 UserPromptSubmit payload→短清單（含絕對路徑、k 上限）；模擬 Read 被推路徑→used 事件（offered=True）、Read 非 offered knowledge→used(offered=False)、Read 非 knowledge→無事件；dream pass 丟棄一個 AGENTS.md 片段；slim brief 不含 dump。
- 跑法：`python3 -m pytest paulshaclaw/memory/tests/`（避開 unittest discover 跳過函式測試的坑）。守住現有 747 綠。

## 8. 驗收

- [ ] 真實 claude session：打一個與某 knowledge 相關的 prompt → context 出現短清單（含可開啟絕對路徑）。
- [ ] Read 該路徑 → `memory_usage.jsonl` 出現 `source:"read", offered:true` 事件。
- [ ] trivial prompt（`/effort`）不注入短清單。
- [ ] dream pass 後新指令檔切片不進 knowledge；`retrieval.db` 不含噪音類。
- [ ] prune dry-run manifest 數字合理、備份就位後才 apply。
- [ ] `psc memory usage` 列出 per-slice read 次數。
- [ ] hook 任一錯誤不影響既有擷取/注入/Read（回歸）。

## 9. 部署順序

1. merge ①②③④⑥⑦ + 測試（hooks 自 repo editable 載入；但 `*_session_*.py`/新 hook 須 install.sh 重新同步到 `~/.agents/memory/hooks/`，見既有部署坑）。
2. settings.json 增掛 UserPromptSubmit（與 codegraph 並存）+ PostToolUse(Read) memory hook。
3. 觀察數日，`memory usage` 看 read 是否累積。
4. ⑤prune：dry-run→備份→核 manifest→apply（獨立 gated）。

## 10. 風險與假設（明列，供 adversarial 挑戰）

- **A1（核心賭注）**：agent 會真的 Read 被推路徑。若不 Read，消費仍 0。緩解：短清單高精度（k≤3）+ 明確提示；但這是全設計命脈。
- **A2**：FTS5 MATCH 吃任意 prompt 文字會語法錯誤/過廣 → 必須 `to_fts_query` 淨化（抽詞 OR 連接）；CJK 分詞品質影響召回。
- **A3**：retrieval.db 最多 1h stale（dream hourly），本 session 剛生的筆記檢索不到。可接受或加輕量 incremental index（後續）。
- **A4**：relevance gate 門檻脆弱——bm25 分數 query-dependent、無界，固定門檻可能過鬆（spam）或過嚴（never fire）。MVP 用「有命中 + top-k cap」，門檻列為可調。
- **A5**：「Read knowledge 路徑 = used」會把「開了但沒用」記為 used（弱於 cited 但遠強於逐字 id）。接受為 proxy。
- **A6**：歸因 Claude-only（PostToolUse）；codex/copilot used 缺測。已接受。
- **A7**：③誤刪——把「指令檔衍生但其實有用的提煉知識」當噪音丟。緩解：分類靠 source 路徑而非標題字串，且刪除限結構性冗餘兩類。
- **A8**：⑤刪 127 筆 live 不可逆（`~/.agents` 非 git）。緩解：強制備份 + dry-run + 人核。
- **A9**：每 prompt 注入增 per-turn latency（sqlite bm25，ms 級）與 context 佔用（k≤3 短行）。評估為可接受。
- **A10**：path 作對齊鍵——若 janitor rename/move slice 檔，offered 的舊 path 與 Read 的新 path 對不上 → 漏記。緩解：offered 映射存 sl_id↔path 雙向，PostToolUse 先比 path 再回退比 sl_id。
