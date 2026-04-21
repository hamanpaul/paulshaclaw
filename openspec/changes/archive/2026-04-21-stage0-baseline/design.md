## Context

Stage 0 tooling foundation 的實作早於 openspec change 流程就緒：Stage 0 本身的任務之一就是「建立 openspec + superpowers 骨架」，在骨架建立完成之前，Stage 0 自身無法走 `propose → apply → archive`。實作已透過 `wt/stage0-tooling-foundation` worktree 完成並合併回 main（commit `7ac043b`），包括 29 條 regression 檢查、tool-matrix、ref-manifest pin、opsx slash-command 雙源、docs-layout convention、workstream 骨架等。

現在需要把 Stage 0 的成果事後追認為 baseline capability，後續 Stage 1–7 的 change（特別是 Stage 3 lifecycle runtime）就能在 openspec workflow 內對 Stage 0 做 diff，而非游離於 change 流程之外。

## Goals / Non-Goals

**Goals:**
- 以單一 capability `stage0-tooling` 把 Stage 0 §8 驗收條目（research/05）全部納入 openspec 的 canonical spec
- 建立「未來任何涉及 Stage 0 範圍的變更必須 MODIFIED/ADDED 此 capability」的契約
- 保留 Stage 0 regression harness 作為 capability 的可執行驗證
- 讓 stage1-baseline / stage2-baseline / stage6-baseline 可依此同模板追認

**Non-Goals:**
- 不重新實作 Stage 0 的任何元件（純追認已落地的工作）
- 不納入 rename PR 流程（使用者決定延後至專案進度 70% 後）
- 不涵蓋 Stage 1+ 的 daemon / memory / security runtime（各自有獨立 baseline change）
- 不修改 Stage 3 canonical contract（該合約凍結動作已於 commit `8fd8166` 完成，與本 baseline 正交）

## Decisions

### Decision 1：反向（reverse）record 而非 forward propose

- **選擇**：事後為已合併到 main 的 Stage 0 工作建 `stage0-baseline` change。
- **替代方案**：
  - (a) 不建任何 change，直接承認 `openspec/specs/stage0/` 即為 canonical — 無法追溯、下游 change 無 diff base。
  - (b) 拆回 worktree、重走 propose → apply 流程 — 成本過高且違反已 merge 事實。
- **理由**：(a) 放棄 Stage 0 §8 驗收的 openspec item 3；(b) 與「最小變更」硬規範衝突；本 decision 是兩者之間最務實的折衷，並讓 spec 與實作保持對應。

### Decision 2：單一 `stage0-tooling` capability 涵蓋全部子系統

- **選擇**：tool-matrix / ref-manifest / worktree helper / sync-ref / regression harness / docs-layout / opsx dual-source / workstream convention / AGENTS 入口 **共用一個 capability**。
- **替代方案**：拆成 `ref-management`、`worktree-helper`、`opsx-commands`、`workstream-convention` 等 4–5 個 capability。
- **理由**：Stage 0 是骨架性階段，子系統彼此耦合（regression harness 檢查 opsx 雙源、opsx 依賴 workstream convention）；拆開會讓多個 capability 需要同時 MODIFIED 才能表達一個變更，徒增 diff 噪訊。等 Stage 0 內某子系統膨脹到複雜度臨界，再以 `## RENAMED Requirements` 拆出獨立 capability 即可。

### Decision 3：rename PR 不納入 baseline

- **選擇**：tool-matrix B 區的 6 個 rename target（`picoclaw-ops-companion`、`obs-auto-moc`、`codex-lesson`、`codex-project-insights`、`session-health`、`coordinator`）在 baseline 中僅以「對照表」形式固化，不宣告 rename 執行條件。
- **替代方案**：納入 requirement「Stage 0 MUST 完成 6 個 rename PR 並將 PR 連結回填 tool-matrix」。
- **理由**：使用者 Q3 決定延後外部 repo PR 至專案進度 >70%；提前寫 requirement 會讓 baseline 狀態變成「未達成」。待 G5-d（in-repo rename）與未來外部 PR 動作時，以 `## MODIFIED Requirements` 更新 Tool rename matrix 的 scenario。

## Risks / Trade-offs

- **Reverse-record 可能遺漏邊緣實作** → Mitigation：對照 research/05 §8 Stage 0 驗收 15 條逐項納入 spec；regression harness 每條 PASS 即反向證據。
- **單一 capability 讓後續 diff 較寬** → Mitigation：要求 MODIFIED 時 copy 整個 Requirement block，並在 commit message 註明 sub-system（tool-matrix / harness / opsx / …）。
- **rename 對照表被誤讀為「MUST 執行」** → Mitigation：design Decision 3 明示；spec 的 scenario 僅驗證「對照表存在且欄位齊全」，不驗證 PR 狀態。

## Migration Plan

- N/A — 本 change 是追認已合併到 main 的工作，無 migration action。
- Rollback：若 archive 後發現 spec 與實際行為不符，以 `## MODIFIED Requirements` 提出修正 change，不需 revert。

## Open Questions

- rename PR 何時啟動？由使用者於專案進度 >70% 時判斷，目前不在 Stage 0 capability 的 scope 內。
- 未來 Stage 0 若擴增新子系統（例如 session-format adapter for Claude Code），是走 `## ADDED Requirements` 還是拆出新 capability？—— 以「能否獨立執行驗證」為切分標準，在該 change 提出時決定。
