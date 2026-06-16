## Context

完整設計全文見 `docs/superpowers/specs/2026-06-16-stage2-content-extraction-design.md`；本檔聚焦技術決策與取捨。

Stage 2 管線骨架健康但核心空心：三家 adapter 只把 payload metadata 餵 `build_session`，不讀 `transcript_path` → inbox 內容全 `(none)`。同時 atomizer 因 project 含 `/` 被 `is_safe_path_component` 擋（`atomize.slices:0`），promoter 從未由 identity 切 LLM。約束：套件為 `pip install -e`（改碼即時生效、不必動部署 hook 副本）；gemma4 (:8001) 目前離線；CC transcript 已設永久保存（`cleanupPeriodDays:999999`）。

## Goals / Non-Goals

**Goals:**
- 三家 adapter 讀 transcript/history 擷取 `user_prompts`/`touched_files` 與標題輸入。
- import 時 per-session gemma4 ≤20 字繁中標題，離線可降級＋補生。
- atomizer 對任意 project 格式 robust、不再 skip。
- 三家既有 payload 可回填。

**Non-Goals:**
- `promoter: identity → llm`（gemma4 原子蒸餾）→ Phase 2。
- 改動部署 hook entry 副本 / 重跑 install.sh。
- 自建 gemma4 服務啟動/維運（本期靠 fallback 脫鉤）。

## Decisions

- **D1 標題在 import、per-session**（非 atomizer promoter）。Promoter 逐 fragment 運作，與「每 session 一條」granularity 不符；import 階段天生 per-session 且標題即時可用。
- **D2 #2 主修＝atomizer 消毒斜線**（`sanitize_project_component`，rich `project` 留 metadata）。替代案：(a) 只補 `projects.yaml`——未登錄專案仍 skip、脆弱；(b) importer 改寫 project 字串——失去 URL rich 形。故選消毒為主（robust、不必維護清單）、projects.yaml 補登為輔（活躍專案得乾淨 slug bucket）。
- **D3 gemma4 離線降級＋補生**。fallback＝首條 prompt 截斷 20 字，標 `title_source: fallback`；import 永不阻塞。替代案：阻塞等 LLM（會丟捕捉）、留空（MOC 無標題）皆拒。
- **D4 內容擷取放 editable adapter／base**（非 hook 端）。改碼下次 hook 觸發即生效、零重新部署；hook 寫進 payload 的 `transcript_path`/`session_id` 已足夠。
- **D5 標題語意**：`assistant_summary` 即設為 ≤20 字標題（使用者要的「摘要成標題」），渲染於 `## Summary` 與 frontmatter `title:`；較長末則內容僅作 gemma4 輸入、不另存（transcript 已永久保存）。
- **D6 promoter 維持 identity**：本期知識層仍為 per-session＋facet 切片，但從此有真內容＋標題。

## Risks / Trade-offs

- gemma4 離線 → 標題暫為 fallback 品質 → 以 `title_source` 標記 + 上線後補生 pass 緩解。
- 消毒改變 knowledge bucket 命名（`/`→`__`）→ 以 projects.yaml 補登活躍專案，使其落乾淨 slug。
- codex prompts 依賴 rollout 檔 → 缺檔則該欄留空、其餘照常（graceful）。
- backfill 覆寫既有 inbox/knowledge → `--dry-run` 預檢 + 可重入。
- 既有 12 筆 claude dead pointer 不可回填 → 留空跳過，可接受。

## Migration Plan

1. 合併後套件即時生效（editable），新 session 自動走新路徑。
2. 手動跑 `backfill.py --dry-run` 預檢 → 正式回填三家。
3. gemma4 上線後對 `title_source: fallback` 者補生標題。
4. Rollback：純套件碼變更、無 schema 遷移，`git revert` 即還原；既回填內容無破壞性。

## Open Questions

- gemma4 服務的啟動與維運歸屬（本期不解，靠 fallback 脫鉤）。
- projects.yaml 活躍專案清單的維護責任（可後續以 evolve 流程固化）。
