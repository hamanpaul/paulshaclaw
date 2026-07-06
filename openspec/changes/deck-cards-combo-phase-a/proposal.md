# Proposal: deck-cards-combo-phase-a

## Why

pipeline 組合技知識（`feature-delivery-pipeline` 的 11-phase 鏈）目前只存在散文 SKILL.md 與使用者腦中，manager 只認手寫的 slice specs——「把 task 拆成 slices + plan + depends_on」全靠人工，dispatch 無法選牌、計分、控成本（#138/#140/#142 缺共用工作單位）。#186 Phase A 把 skill/persona 卡片化為機器可讀的宣告層，讓「一句 task + 一張 combo」可編譯成既有 manager 直接代管的 specs，**manager runtime 零改動**。

設計真相源：`docs/superpowers/specs/2026-07-06-deck-cards-combo-design.md`（已含 Codex 對抗審查 7 Important + 1 Minor 修正）。

## What Changes

- 新增 `paulshaclaw/deck/` 包：Card/Combo YAML schema（fail-closed 載入）、combo 編譯器（combo+task → slice specs）、produces glob 驗收器、CLI。
- 新增 `deck/data/cards.yaml`（自 `feature-delivery-pipeline` 轉錄的 skill 卡）與 `deck/data/combos/{feature-oneshot,mcu-feature}.yaml` 兩張 combo。
- `paulshaclaw/cli.py` 新增 `deck` route（現行僅 `{memory|coordinator}`），`tests/test_psc_cli.py` 同步。
- `persona/personas.yaml` 各 role 新增 `skills:` 欄位；`persona/{loader,contract}.py` 讀取、保留並 shadow 驗證引用（loader 現行會丟棄未知欄位）。
- 編譯輸出安全預設：預設 dry-run、`--emit` 一律 `dispatch: hold`、同名拒絕需 `--force`、flat 檔名 `<slice_id>.md`。
- 對 `paulshaclaw.lifecycle`／`paulshaclaw.memory` 零 import（hippo 拆分協調，設計 §9）。

## Capabilities

### New Capabilities
- `deck-schema`: Card/Combo 資料模型與 fail-closed 載入驗證（欄位、佔位符、interactive/headless 分型、class 分級）
- `deck-compile`: combo+task 編譯為 manager 可代管的 slice specs（additive/--only 規則、佔位符代入、emit 安全語意、specs 目錄解析鏡射 manager 契約）
- `deck-verify`: 卡片 produces glob 存在性驗收（exit code 供 CI/gate；翻 auto 前人工 checklist）
- `deck-data`: 兩張實戰 combo 的卡片轉錄（feature-oneshot、mcu-feature），兼 schema 泛化性驗證
- `persona-skills-binding`: personas.yaml `skills:` 欄位與 loader shadow 驗證（skill↔persona 首次接線）

### Modified Capabilities
（無——不動既有 capability 的 requirement；coordinator/manager runtime 行為零改動）

## Impact

- 新增：`paulshaclaw/deck/**`、`deck/data/**`、對應 `tests/`。
- 修改：`paulshaclaw/cli.py`（+deck route）、`tests/test_psc_cli.py`、`persona/personas.yaml`、`persona/loader.py`、`persona/contract.py`。
- 不動：`coordinator/**`（W7 整合測試唯讀 import）、`lifecycle/**`、`memory/**`（零 import 鐵律）。
- 依賴/協調：#213（#91 facade）merge 後補 `specs_dir()` 切換；hippo `memory-extraction-hippo` §4.2 與 W5 在 `persona/contract.py` 有不同行交會（先落地者贏、後者 rebase）。
- 佈署面：無 runtime/服務變動；`psc deck` 為純本地 CLI。
