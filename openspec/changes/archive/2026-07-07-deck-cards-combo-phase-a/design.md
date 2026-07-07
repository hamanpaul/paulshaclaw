# Design: deck-cards-combo-phase-a

> 完整執行設計（含 Codex 對抗審查修正紀錄）：`docs/superpowers/specs/2026-07-06-deck-cards-combo-design.md`。本檔為 change 內濃縮版，落地細節以該檔為真相源。

## Context

manager control-plane（#187）已通電：specs 佇列 → `depends_on` DAG → headless fan-out → handoff manifest。但 specs 全靠手寫；pipeline 組合技知識只存在 `feature-delivery-pipeline` 散文 SKILL.md。#186 要補的是宣告層 + 編譯器，不是 runtime。

限制條件：hippo 拆分（`memory-extraction-hippo`）將平移 `lifecycle/**` 並要求全 repo `paulshaclaw.lifecycle|memory` import 清零；persona guardrail 全域 shadow；#213（#91 facade）in-flight 且 capability 清單無 `specs_dir`。

## Goals / Non-Goals

**Goals:**
- 卡片/combo 成為可版本化 artifact；`psc deck compile <combo> --task ... --emit` 產出 manager 可代管的 hold specs。
- 兩張實戰 combo（feature-oneshot、mcu-feature）轉錄完成並通過 parse-level 整合驗證。
- persona↔skill 首次接線（shadow）。

**Non-Goals:**（詳見設計 §12）選牌自動化、`/dispatch` 接線、hit ledger/park、provider_binding 生效、custom-skills frontmatter 回灌、coordinator/manager runtime 任何改動、enforce 翻牌。

## Decisions

1. **薄宣告層 + 編譯器，否決 runtime combo engine**：站穩閘觀察期不動 runtime；接點是檔案不是 code。
2. **零 import 鐵律**：deck 不 import `paulshaclaw.lifecycle`/`paulshaclaw.memory`（hippo §4.5 清零相容）；schema/glob/frontmatter 全自足。W7 測試經 coordinator import 鏈的間接依賴屬 tests 層，明文豁免。
3. **安全預設**：dry-run 預設、`--emit` 一律 `dispatch: hold`、同名拒絕 + `--force`、flat `<slice_id>.md`（`scan_specs` 非遞迴）。hold 保證範圍=automatic ready/fanout；`force_hold` 手動覆寫視為 operator 授權。
4. **specs 目錄解析鏡射 manager 契約**（`PSC_MANAGER_SPECS_DIR` → `~/.agents/specs`）+ 相等性測試；facade 落地後補 `specs_dir()` 切換。
5. **additive fail-closed**：`--with` 顯式 `:after=/:before=` 優先；pattern 覆蓋推斷無法證明 → 要求明示位置。`--only` 才排他。
6. **requires/produces 為 compile-time/report-only**：runtime 只認 frontmatter 四欄位；機器 gate 留 Phase B。
7. **persona 卡不複製資料**：cards.yaml 只收 skill 卡；persona view 由 personas.yaml 衍生；loader 需保留 `skills:`（現行會丟棄未知欄位）。

## Risks / Trade-offs

- [卡片與 SKILL.md 散文漂移] → 欄位極簡、produces 只寫可機械驗證 glob；SKILL.md 維持人讀真相源。
- [schema 過早凍結] → W2 第二 combo 當泛化壓力測試；schema `version: 0` 預留遷移。
- [活佇列誤觸發] → hold-by-default + dry-run + 同名拒絕三道防線。
- [與 hippo 撞檔] → 零 import + facade 鏡射 + `persona/contract.py` 不同行交會（先落地者贏、後者 rebase）。
- [W3 等 #213] → 不阻塞：deck 內部 helper 先行，facade 合入後一行切換。

## Migration Plan

純新增 + 兩個小修改點（cli route、persona loader），單 PR 可回滾（revert 即可，無資料遷移、無服務變動）。

## Open Questions

- facade `specs_dir()` 提案由本 change 附帶開 issue 還是併入 #91 —— 落地時裁決。
