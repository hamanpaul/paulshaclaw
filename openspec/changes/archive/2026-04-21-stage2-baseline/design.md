## Context

Stage 2 paulsha-memory 階段實作於 worktree `wt/stage2-paulsha-memory` 完成，最終以 `--no-ff` 合併到 main（merge commit `2da5ccb`）。本階段落地的是 **spec/docs-level baseline**，不含 Python 執行時碼 —— 路由、janitor、replay 在當前階段仍以設計文件形式確定邊界，實際 runtime 要在 Stage 3 lifecycle engine 啟動後才會 bind。合併前由 `superpowers:code-reviewer` 對照 Stage 3 canonical contract 做 7 項檢查，其中 item 5（Stage 3 frontmatter 欄位名稱具體列舉）原為 FAIL，已透過 fixup commit `6cc4356` 在 merge 前修復，7 項全部 PASS。

## Goals / Non-Goals

**Goals:**
- 以單一 capability `stage2-memory-governance` 收納 Stage 2 §8 驗收全部項目
- 讓 Stage 3 的 artifact / event 消費契約（frontmatter schema、`decayed/reactivation`、`inbox → work-centric → knowledge`）可被 spec 層追溯
- 保留 `stage2_integration_check.sh` 的 7 條檢查作為 capability 的可執行驗證
- 為 `ops-companion`（Stage 6）消費 provenance 欄位提供穩定契約

**Non-Goals:**
- 不納入 Python 執行時碼（importer / classifier / replay 當前僅為 `.md` 邊界宣告）
- 不修改 Stage 3 canonical contract 或 Stage 1 daemon 介面
- 不決定外部 PR sync-back 時機（延後至專案進度 >70%）
- 不處理 review 的兩條 Minor 項（routing.md 完整 phrase grep、review.md 「可合併」自評）—— 留作 follow-up change

## Decisions

### Decision 1：reverse-record 與 Stage 0/1 對齊

- **選擇**：事後為 merge commit `2da5ccb` 已合併到 main 的 Stage 2 工作建 `stage2-baseline` change。
- **替代方案**：(a) 直接把 `openspec/specs/stage2/scope.md` 視為 canonical；(b) 三分切 importer/classifier/replay 為獨立 capability。
- **理由**：Stage 0/1 baseline 已採 reverse-record；保持同一模式讓 Stage 3 runtime change 的 MODIFIED 對象統一。

### Decision 2：spec-level baseline 而非 runtime baseline

- **選擇**：本 capability 的 requirement 以「路由契約」「事件定義」「sync-back gate 條件」「integration 檢查存在」為主體，不規範 Python 類別/函式。
- **替代方案**：等 importer/classifier/replay 有 Python 實作再建 baseline。
- **理由**：Stage 3 lifecycle engine 需要先知道 Stage 2 的事件與 frontmatter 欄位才能設計 artifact 產出；延後 baseline 會讓 Stage 3 設計失去對齊基準。spec-level baseline 足以提供 diff 原點；等執行時碼落地，再以 `## ADDED Requirements` 追加執行層 requirement。

### Decision 3：在 merge 前執行 review fixup 而非 follow-up

- **選擇**：code review item 5（frontmatter 欄位具體列舉）直接在 worktree 上補 commit `6cc4356` 後再 merge，不留到 follow-up change。
- **替代方案**：把 item 5 記為 follow-up，允許 baseline 有已知不足。
- **理由**：Stage 2 scope 文件一旦合併就會成為 Stage 3 runtime 設計的輸入；若 frontmatter 欄位未名列，Stage 3 可能因為漏項而設計偏差。此 fix 僅 3 個檔案 10 行差異，低風險、立即可測，符合「最小變更 + 不留已知缺口」原則。

## Risks / Trade-offs

- **spec-level baseline 無執行時守衛** → Mitigation：`stage2_integration_check.sh` 的 7 條 `grep -Fq` 作為 literal 保護；任何語義 drift 會讓 check 失敗。
- **單一 capability 讓未來 diff 較寬** → Mitigation：MODIFIED 時 copy 整段 Requirement，commit message 註明 sub-system（routing / janitor / events / gate）。
- **fixup 後的 code review 沒再跑一輪** → Mitigation：修改範圍極小（三處字串、一處新增 require_text），integration check 已驗證欄位出現；如未來發現漏洞以 `## MODIFIED Requirements` 修正即可。

## Migration Plan

- N/A — 本 change 追認已合併到 main 的工作。
- Rollback：spec 偏差時以 `## MODIFIED Requirements` 追加變更，不 revert merge commit `2da5ccb`。

## Open Questions

- importer / classifier / replay 的 Python 執行時碼何時落地？預計於 Stage 3 lifecycle engine 啟動後同步進行，屆時以 `## ADDED Requirements` 加入執行層 requirement。
- janitor systemd 單位於 Stage 7 deploy 階段實際定檔時，本 capability 是否需要 MODIFIED？—— 視 Stage 7 runtime 決定。
