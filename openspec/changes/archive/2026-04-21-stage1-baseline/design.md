## Context

Stage 1 是 paulshaclaw 的第一個 runtime 階段，提供 daemon / TUI / Telegram bot 三者組成的 PaulShiaBro 最小可跑版。實作於 worktree `wt/stage1-core-daemon-tui-bot` 完成、通過 12 條 smoke test，並於 2026-04-21 以 `--no-ff` 合併到 main（commit `49d2739`）。合併前由 `superpowers:code-reviewer` 對照 Stage 3 canonical contract v0.1 §2 做 7 項合規檢查，全部 PASS。

本 change 的目的是把已合併工作事後追認為 openspec baseline capability，讓 Stage 3 及其下游（Stage 4/5/7）的 runtime change 能以 `## MODIFIED Requirements` / `## ADDED Requirements` 形式在 openspec workflow 內做 diff。

## Goals / Non-Goals

**Goals:**
- 以單一 capability `stage1-core-runtime` 把 Stage 1 §8 驗收全部納入 canonical spec
- 確保 Stage 3 canonical contract §2.2/§2.3/§2.4/§2.5 所要求的 Stage 1 介面欄位在 spec 內可被 diff
- 保留 `tests/test_stage1_smoke.py` 的 12 條案例作為 capability 的可執行驗證
- 建立 Telegram authz gate 的白名單語義基線，供 Stage 6 audit 消費

**Non-Goals:**
- 不擴充 daemon 到 Stage 3 lifecycle 語義（gate 判斷、phase 轉移由 Stage 3 實作，daemon 只負責 `/dispatch` 轉發 payload）
- 不引入 async runtime / uvloop / websocket（保持 Python stdlib subprocess-friendly 介面）
- 不涵蓋 Telegram bot 的 webhook / long-poll 實際連線層（當前只有 router 邏輯；連線層待 Stage 7 deploy 時決定）
- 不處理 code review 遺留的兩條 Important polish：`PaneAssignment` 型別檢查、`allowed_user_ids` 錯誤訊息（以 follow-up change 形式處理）
- 不修改 Stage 3 canonical contract（該合約由 Stage 3 baseline change 擁有）

## Decisions

### Decision 1：reverse-record 而非 forward propose

- **選擇**：事後為 commit `49d2739` 已合併到 main 的 Stage 1 工作建 `stage1-baseline` change。
- **替代方案**：
  - (a) 不建 change，直接承認 `openspec/specs/stage1/README.md` 為 canonical — 但 README 目前只是 placeholder，無 requirement 結構可 diff。
  - (b) 把 Stage 1 拆成 daemon / TUI / bot 三個 forward change 重走流程 — 成本過高且不符已 merge 事實。
- **理由**：與 `stage0-baseline` 採一致模式，讓所有 Stage N baseline 皆為 reverse-record；下游 Stage 3 change 得以在統一 workflow 下 diff。

### Decision 2：單一 `stage1-core-runtime` capability

- **選擇**：daemon / config / coordinator seam / TUI / Telegram bot / sample config / smoke test 共用一個 capability。
- **替代方案**：拆成 `daemon-runtime`、`config-seam`、`telegram-bot`、`tui-renderer` 等 4 個 capability。
- **理由**：Stage 1 子系統彼此耦合（Telegram router 直接呼叫 daemon；CLI 透過 `load_config` + daemon handler）；拆開會讓一個變更（例如調整 `/dispatch` 回傳欄位）需要同時 MODIFIED 三個 capability。等 Stage 1 內某子系統複雜度臨界時，再以 `## RENAMED Requirements` 拆出獨立 capability。

### Decision 3：契約側重 shape，不側重實作細節

- **選擇**：spec 以「JSON 回傳欄位」、「config precedence 順序」、「authz 黑白名單行為」為 requirement 主體，不規範具體型別或錯誤訊息字串。
- **替代方案**：把 `PaneAssignment` 的每個欄位型別、`allowed_user_ids` 的錯誤訊息文字都寫成 requirement。
- **理由**：shape 是 Stage 3 下游的硬依賴；型別細節屬於內部實作，code review 已標示兩條 polish，留給 follow-up change 處理，不綁死在 baseline spec。

## Risks / Trade-offs

- **spec 過寬導致下游誤用** → Mitigation：requirement 的 scenario 直接對應 `tests/test_stage1_smoke.py` 案例，任何 shape 變動必被 test 攔截。
- **單一 capability 讓後續 diff 較寬** → Mitigation：要求 MODIFIED 時 copy 整個 Requirement block，且在 commit message 註明 sub-system（daemon / config / bot / tui）。
- **code review 兩條 Important polish 未納入 baseline** → Mitigation：以 follow-up change 追加；baseline 保持與合併版本一致，避免 spec 與 main 分岔。

## Migration Plan

- N/A — 本 change 追認已合併到 main 的工作，無 migration action。
- Rollback：若 archive 後發現 spec 與實際行為不符，以 `## MODIFIED Requirements` 提出修正 change，不 revert commit `49d2739`。

## Open Questions

- Telegram bot 連線層（webhook vs long-poll）於 Stage 7 deploy 決定；屆時以 `## ADDED Requirements` 補上對應 scenario。
- `LocalCoordinator` 是否保留為 runtime 預設？Stage 3 啟動後若完全以 lifecycle engine 取代，是以 `## REMOVED Requirements` 移除、還是以 `## MODIFIED Requirements` 調整預設實作？—— 待 Stage 3 baseline change 提出時決定。
