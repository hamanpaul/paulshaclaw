## Context

Stage 6 原始工作在舊基線分支完成，若直接 merge 到 main 會把 G1~G3 已完成成果一起回退。為維持「最小必要變更 + 不覆蓋已完成項」，本次採用 `cherry-pick 604f0b0 + fdb229a` 收斂 Stage 6 內容，再補 OpenSpec archive 反向記錄。修正點包含：保留 Stage 0 的通用 sync-back gate 文案，不讓 Stage 6 特化文案覆蓋 shared 規範。

## Goals / Non-Goals

**Goals:**
- 建立 Stage 6 的 canonical capability (`stage6-security-governance`)
- 保證 `/ship`/`git push`/deploy/package/remote 高風險 gate 合約可追溯
- 保證 redaction 與 append-only audit 的最低驗證契約可重放
- 對齊 Stage 0~2 已採用的 archive 反向記錄格式

**Non-Goals:**
- 不做 upstream rename PR（依當前策略 postpone）
- 不在本 change 中擴充大規模 redaction fuzz corpus
- 不修改 Stage 7 deploy 流程實作

## Decisions

### Decision 1: 使用 cherry-pick 而非直接 merge worktree

- **選擇**：cherry-pick `604f0b0`、`fdb229a` 至 main。
- **理由**：避免舊分支與 main 的大量歷史差異造成覆寫/刪除已完成項。

### Decision 2: 保留 shared sync-back gate 文案

- **選擇**：`scripts/sync-ref.sh` 維持「回寫 custom-skills 前，必須先通過對應 stage 測試並保留證據」。
- **理由**：shared 規範屬 Stage 0 成果，Stage 6 不應縮窄成單一工具專屬規範。

### Decision 3: Stage 6 以 spec-driven 反向記錄

- **選擇**：新增 `openspec/changes/archive/2026-04-21-stage6-baseline/*`，同步 canonical spec `openspec/specs/stage6-security-governance/spec.md`。
- **理由**：與 stage0/1/2 收斂模式一致，提供後續 Stage 7+ 變更的 diff 基準。

## Risks / Trade-offs

- cherry-pick 後仍需人工確認 shared 文件未被 stage 特化覆蓋。
- Stage 6 現階段測試以 unittest 為主，fuzz 深度仍有限。

## Migration Plan

- 無資料遷移。
- 回滾策略：若 Stage 6 行為需調整，以後續 `## MODIFIED Requirements` 變更 capability 規格，不回退 G1~G3 已合併內容。
