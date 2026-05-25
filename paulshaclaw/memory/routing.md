# Stage 2 Memory Routing

## 1. Pipeline 概觀

`paulsha-memory` 以 deterministic pipeline 處理記憶輸入：

1. `importer`
   - 從 session distilled artifact、plan、research、report 收件到 `inbox/`
   - 附上來源、時間、workstream、artifact 類型
   - 進入 `inbox/` 前必須先遵守 Topic 8 memory security policy（`external_to_raw` / `raw_to_distilled` 的 redaction、classification、audit 契約）
2. `classifier`
   - 依內容把項目送往 `work-centric/` 或 `knowledge/`
   - 補上 `atomized_from`、`record-agent-reference` 與引用關係
3. `replay`
   - 從 `work-centric` 與 ledger 事件組 replay bundle
   - 提供給後續 workflow 做復盤、handoff、re-activation 判斷

## 1.1 MVP 實作邊界

本 repo 已落地的 Stage 2 Importer MVP 以 `paulshaclaw/memory/importer/` 與
`paulshaclaw/memory/hooks/` 為主：

1. hook scripts 只負責把 Claude / Codex / Copilot 的 session payload 寫進
   `runtime/queue/`
2. importer 做 adapter 正規化、frontmatter/render、project resolver、classifier、
   idempotent ledger、`inbox/{sessions,plans,research,reports}/` 路由
3. `work-centric -> knowledge` 的升級、replay、janitor、`decayed/reactivation`
   仍沿用本文件既有 Stage 2 治理邊界，屬於後續 runtime slice

MVP 設計與驗證細節見：

- `docs/superpowers/specs/2026-05-24-stage2-memory-importer-mvp-design.md`
- `openspec/changes/stage2-memory-importer-mvp/`

`obs-auto-moc` watcher 只保留介面契約與 follow-up 指向，實作不在本 repo archive 內。

## 2. inbox -> work-centric -> knowledge 路由

| 來源 | 初始落點 | 升級條件 | 目標落點 |
|---|---|---|---|
| session distilled output | `inbox/sessions/` | 已綁定 project/workstream | `work-centric/<project>/experience/` |
| plan / task / todo artifact | `inbox/plans/` | 仍為進行中上下文 | `work-centric/<project>/plan/` |
| research / report | `inbox/research/`、`inbox/reports/` | 可重用且具引用 | `knowledge/concepts/`、`knowledge/methods/` |
| 已驗證事件摘要 | `inbox/reports/` | replay 仍可重建脈絡 | `knowledge/incidents/`、`knowledge/entities/` |

## 3. decayed/reactivation 事件流程

1. classifier 或 janitor 偵測條目需要降權時，寫入 `decayed` 事件。
2. 條目保留原 citation，但從高信任檢索集合移出。
3. 若後續有新證據、人工確認或 replay bundle 支持，寫入 `reactivation` 事件。
4. 重新啟用時必須同時記錄：
   - 觸發來源
   - replay bundle / workstream 關聯
   - 最新 `record-agent-reference`

## 4. 驗證邊界

Stage 2 integration gate 最少要覆蓋：

- importer 可把 artifact 放到正確 inbox 類別
- importer 與 replay/dry-run 必須透過 `paulshaclaw.memory.policy` 執行 Topic 8 安全邊界，不得自行旁路 policy
- classifier 可把內容從 `inbox` 升級到 `work-centric` 或 `knowledge`
- replay 可從 ledger 與 work-centric 組出可追溯脈絡
- `decayed/reactivation` 事件可被寫入並被 janitor 掃描
