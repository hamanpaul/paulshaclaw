# Memory 消費迴路 — Handoff（2026-06-29）

> 狀態：消費迴路（PR #156，squash `98305aa`）已 **merge + 部署 + 端到端驗證 live**。
> 本檔交接兩個**未解決的後續項**。設計/計畫見 `docs/superpowers/{specs,plans}/2026-06-29-memory-consumption-loop-*`；capability spec 見 `openspec/specs/stage2-memory-{prompt-retrieval,read-attribution}/` 與 `openspec/changes/archive/2026-06-29-stage2-memory-consumption-loop/`。

## 已完成（baseline）

- UserPromptSubmit 任務條件式 bm25 短清單注入（含絕對路徑）→ agent native Read 拉全文 → PostToolUse(Read) read-based 歸因（`memory_usage.jsonl` 記 `source:read, offered:bool`）。
- `build_index` 防禦性排除 `classify_noise` 命中 + `pool_exclude_reason`（canary/review）。SessionStart brief 瘦成 orientation。usage CLI 改 read-based。
- 部署：`install.sh` 複製 3 新 hook + 接 settings.json（UserPromptSubmit 與 codegraph 並存、PostToolUse matcher=Read）。實機 smoke 通過（含 symlink 路徑對齊）。
- 部署當下 `retrieval.db` = 126 indexed rows（總 knowledge 232）。

---

## 開放項 3：broad-corpus 過度排除真知識（retrieval 側，非破壞，**優先**）

### 觀察（2026-06-29 實機數據）
`moc/runner.run_moc` 呼叫 `search.build_index(..., doc_corpus=instruction_corpus.load_corpus())`，`load_corpus()` 用**broad default roots**（`~/.claude/CLAUDE.md`、`~/CLAUDE.md`、`~/AGENTS.md`、`~/.codex`、`~/.agents`、`~/prj_pri`、`~/prj_arc`…）。對 doc-fragment 做逐字比對排除後，各 project 被排除於檢索之外的比例：

| project | total | indexed | excluded |
|---|---:|---:|---:|
| testpilot | 82 | 29 | **53（65%）** |
| serialwrap | 74 | 26 | **48（65%）** |
| paulshaclaw | 46 | 41 | 5（11%） |
| paulsha-conventions / paul_chen / airoha | — | =total | 0 |

### 風險
testpilot / serialwrap 的 per-project `AGENTS.md` **內嵌真架構知識**（RPC routing / session 狀態機 / WAL 等，見 [[project_doc_fragment_corpus_scoping]]），broad corpus 會把「verbatim 命中 AGENTS.md 段落」的**真知識**判為 doc-fragment 而排除。65% 排除率高度疑似**過度排除**→ 消費迴路對這兩個 project 形同半盲（短清單檢索不到大半知識）。paulshaclaw 11% 才合理（其 AGENTS.md 片段確為噪音）。

### 為何不靠 prune 解決
此為**檢索側排除（非刪除、可恢復）**；prune-noise 已驗證對安全 scope（paulshaclaw/structural/empty）= 0 可刪，testpilot/serialwrap 的 doc-fragment 正是過刪風險區，**不可刪**。問題在 `build_index` 的 corpus 範圍，不在 prune。

### 建議方向
- 讓 `build_index` 的 doc_corpus **per-project scoped**（鏡像 `prune-noise --project` 的既有作法）：每個 project 只用「該 project 實際看得到的 instruction docs」當 corpus，而非全域 broad roots。
- 或對 testpilot/serialwrap 改用該 repo 的 `AGENTS.md` 當 scoped corpus、並加「逐字命中但屬該 repo 真架構段落」的 allowlist/排除清單。
- **驗證關卡**：動 corpus 前，抽樣被排除的 testpilot/serialwrap 筆記，人工確認其為真噪音或真知識，再決定門檻（沿用「dry-run 核 manifest、數字超預估就停」原則）。

---

## 開放項 4：read 訊號回授 relevance / decay（#148 剩餘子項）

### 現況
read-based `used` 事件已落地 `runtime/ledger/memory_usage.jsonl`（`source:read`、`offered:bool`、`sl_id`、`project`）；`psc memory usage` 已可聚出 per-slice `offered_count / read_count / last_read / never_read`。但訊號**尚未回授**到任何決策——純記錄。

### 建議方向（另立 change，非本 PR 範圍）
1. **relevance 排序**：把 `read_count`（近 N 天衰減）併入 `search.search` 的排序（現為 `bm25 - 0.1*link_weight`），讓常被 Read 的 slice 在短清單排前。
2. **janitor decay**：把 `never_read`（offered 多次但 read=0）餵給 janitor 當 decay 訊號之一——但需先確認 janitor 真在跑（沿 #100 R2 硬前提），且 read 樣本量足夠（部署初期 read 稀疏，勿過早 decay）。
3. **gating**：先累積數日 read 數據（用 `psc memory usage` 觀察），有統計意義再接回授；否則 cold-start 會用噪音訊號做決策。

### 關聯
- 父 issue **#148**（消費端可觀測性：usage 訊號 + 回饋 relevance/decay）—— 本迴路答了「是否真用＝read 歸因」，**「回饋 relevance/decay」即本項，仍 open**。
- 量測效度背景見 RCA：逐字 cited/matched 是假 0、已退役（`usage.py` 標 deprecated）。

---

## 操作備忘
- 迴路對**新 session** 生效（settings.json 在 session 啟動讀）。
- 部署是**複製非 symlink**：改 hook 後須重跑 `install.sh` 重新同步（見 [[feedback_hook_deploy_copy_not_symlink]]）。
- knowledge 備份：`~/.agents/backup/knowledge-preprune-20260629-*.tar.gz`。
- 驗證用 `python3 -m pytest paulshaclaw/memory/tests/`（勿用 unittest discover）。
