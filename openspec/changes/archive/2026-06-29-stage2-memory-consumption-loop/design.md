## Context

完整設計定稿於 `docs/superpowers/specs/2026-06-29-memory-consumption-loop-design.md`（brainstorm 產出），本文濃縮其架構決策供 spec/tasks 對齊。

現狀：記憶生產端（importer→atomize→promote→dream→MOC→index）穩定；消費端 telemetry 6 筆全 `0/0`。6-agent RCA workflow 結論——0 引用過度決定，主因依序為：內文從未遞送（brief 只給標題索引 + 8 條一行摘要、`[[stem]]` 在 Claude Code 不可 dereference）、量測不到（逐字 16-hex id / 標題偵測器）、任務盲檢索（SessionStart 只吃 project+時間，真正 bm25 ranker 只接手動 CLI）、池子噪音（55% 為已在 system prompt 的 AGENTS.md 片段）。

約束：所有 hook best-effort、exit 0、不阻斷 prompt/tool（沿 #141）；不改 hourly dream 主流程；`~/.agents` 非 git（刪除不可 undo）；retrieval.db 每小時 rebuild。

## Goals / Non-Goals

**Goals:**
- 相關記憶**內文**在對的時機確實進得了 agent context，並被實際取用（消費優先）。
- 「使用」被精準、低摩擦地量測（read=used），取代假 0 的逐字偵測。
- 生產端、池端、存量三處噪音一次治理。

**Non-Goals:**
- codex/copilot 的 read 歸因（先 Claude-only；二者仍收短清單可 Read）。
- 強制 agent 必讀（仍依賴短清單精度 + 提示）。
- relevance 回授 decay / 重排（後續另案，需先有 read 數據）。
- 改動 hourly dream/atomize/janitor/MOC 主流程。

## Decisions

- **遞送 ⊕ 歸因＝Hybrid（推短清單 + 拉全文）**，而非 push-only 全文注入或 pull-only recall 工具。推保證相關內文進得了 context（消費），拉（native Read）保證精準歸因，token 可控。push-only 歸因會因內容重疊假陽性；pull-only 與「消費優先」相悖（agent 可能不主動拉）。
- **拉取走 native Read + PostToolUse 歸因**，而非新建 recall CLI/MCP。對 agent 零新概念、最低摩擦；代價是精準歸因限有 PostToolUse 的 Claude Code，codex/copilot 退化為缺測（已接受）。
- **檢索移到 UserPromptSubmit、複用既有 `search.py` bm25**，而非沿用 SessionStart project dump。prompt 為查詢，relevance 才結構性可能。需 `to_fts_query` 淨化任意 prompt 文字避免 FTS5 語法錯誤。
- **對齊鍵＝session_id + 絕對路徑**（PostToolUse 唯一可靠拿到的是 file_path）；offered 映射存 sl_id↔path 雙向，path 對不上時回退比 sl_id（容忍 janitor rename）。
- **噪音治理重用既有、只補 index/pool 排除**：spec 盤點發現 `stage2-noise-governance`（#147）已具備 doc-fragment（CLAUDE.md/AGENTS.md/GEMINI.md 逐字片段）+ structural-echo/empty/placeholder 的 `classify_noise`、產生端丟棄與 `prune-noise` CLI——即我原以為要新造的「agents-md-fragment / 空 session-metadata」。故**不重造**：殘留 ~127 筆是 corpus scoping 操作缺口，以既有 `prune-noise --project`（dry-run gated）清除。真正新增者僅：(a) `build_index`/slim brief 對 `classify_noise` 命中者 defense-in-depth 排除（殘留未 prune 也不進短清單）；(b) `canary-fixture`/`review-record` 非刪除級池排除。
- **SessionStart brief 瘦成 orientation、移除 16-hex 前言**；offered 改 per-prompt。
- **telemetry 主訊號改 read-based**，退役逐字 cited/matched；no-op/短 session 因「無 prompt→無 offered→無 used」自然不再產假 0 列。

## Risks / Trade-offs

- [agent 不 Read 被推路徑 → 消費仍 0（核心賭注）] → 短清單高精度（k≤3）+ 明確提示；read 數據將驗證此假設成立與否。
- [FTS5 MATCH 吃任意 prompt 文字會語法錯/過廣] → `to_fts_query` 抽 alnum/CJK token OR 連接；CJK 分詞品質影響召回，列為可調。
- [relevance gate 門檻脆弱（bm25 無界）] → MVP 用「有命中 + top-k cap」，門檻參數化、之後依 read 數據調。
- [retrieval.db 最多 1h stale，本 session 新筆記檢索不到] → 接受；incremental index 列後續。
- [Read=used 把「開了沒用」記為 used] → 接受為 proxy（弱於 cited 但遠強於逐字 id）。
- [刪 127 筆 live 不可逆] → 強制備份 + dry-run + 人核 manifest（數字超預估即停）。
- [誤刪指令檔衍生的有用知識] → 分類靠 source 路徑、刪除限結構性冗餘兩類。
- [每 prompt 注入增 latency/context] → sqlite bm25 ms 級、k≤3 短行，評為可接受。

## Migration Plan

1. merge 檢索/歸因/生產過濾/池過濾/brief 瘦身/telemetry 整併 + 測試（守 747 綠）。
2. `~/.claude/settings.json` 增掛 UserPromptSubmit（與 codegraph 並存）+ PostToolUse(Read) memory hook；`install.sh` 重新同步 hooks 到 `~/.agents/memory/hooks/`。
3. 觀察數日，`psc memory usage` 看 read 是否累積。
4. prune（獨立 gated）：dry-run → 備份 `knowledge/` → 人核 manifest → `--apply`。
- 回滾：移除兩個新 hook 註冊即停用迴路；telemetry/brief 改動可 git revert；已刪 live 筆記靠步驟 4 備份還原。

## Open Questions

- relevance gate 門檻具體值（先參數化、依 read 數據定）。
- canary-fixture/review-record 是否日後也納入生產端丟棄（先只池端排除觀察）。
- codex/copilot read 歸因的後續做法（PostToolUse 等價物或 wrapper）。
