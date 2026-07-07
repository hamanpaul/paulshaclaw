# Tasks: deck-cards-combo-phase-a

> Lane 標注對應設計 §10：W0 為 barrier（先行單點），W1–W5 五條 lane 互不撞檔可平行派工（各自 branch/worktree），W7 為整合節點。TDD：各 code 任務 RED 先行。

## 1. W0 schema 凍結（barrier，先行）

- [ ] 1.1 建 `paulshaclaw/deck/` 骨架（`__init__.py`、`schema.py`）與 `tests/test_deck_schema.py`（RED）
- [ ] 1.2 實作 Card/Combo dataclass + fail-closed validator（欄位、枚舉、未知 ref、depends_on 環、佔位符白名單）
- [ ] 1.3 frontmatter 契約對齊測試：斷言編譯輸出欄位集合 == `parse_spec_frontmatter` 接受集合（dispatch/slice_id/plan/depends_on）
- [ ] 1.4 deck 包 import-lint 測試（禁 `paulshaclaw.lifecycle`/`paulshaclaw.memory`）
- [ ] 1.5 schema v0 凍結：`version: 0` 欄位 + 範例 YAML 定稿（W1–W5 fan-out 的共用合約）

## 2. W1 feature-oneshot 轉錄（lane，平行）

- [ ] 2.1 `deck/data/cards.yaml`：自 `feature-delivery-pipeline` SKILL.md 轉錄 11 phase 卡片（interactive/headless 分型、produces 僅機械可驗 glob、class 分級）
- [ ] 2.2 `deck/data/combos/feature-oneshot.yaml`：卡序 + depends_on + gate_spine
- [ ] 2.3 載入驗證測試：cards.yaml + feature-oneshot 通過 schema 全驗證、11 phase 全對應

## 3. W2 mcu-feature 轉錄（lane，平行）

- [ ] 3.1 `deck/data/combos/mcu-feature.yaml` + MCU 特有卡增補（轉錄自 `mcu-coding-skill`）
- [ ] 3.2 泛化性回饋：轉錄中 schema 表達不了的結構回饋 W0 修訂（不硬塞）
- [ ] 3.3 載入驗證測試：與 feature-oneshot 同一驗證鏈通過

## 4. W3 compile 編譯器（lane，平行）

- [ ] 4.1 `tests/test_deck_compile.py` RED：headless-only 產出、interactive checklist、佔位符代入、slug 正規化（branch-safe ≤60）
- [ ] 4.2 實作 `deck/compile.py` 核心：combo+task → slice specs（`<task-slug>-<card-id>`）+ 編譯報告
- [ ] 4.3 requires pattern-level 覆蓋檢查 + `--allow-external`；缺 `--change` 報錯
- [ ] 4.4 additive：`--with card[:after=|:before=]` 顯式定位、推斷 fail-closed；`--only` 排他
- [ ] 4.5 emit 安全語意：預設 dry-run、`--out`、`--emit` 一律 hold、flat `<slice_id>.md`、同名拒絕 + `--force` 原子覆蓋
- [ ] 4.6 specs 目錄 helper（鏡射 `PSC_MANAGER_SPECS_DIR` → `~/.agents/specs`）+ 與 manager_daemon 預設相等性測試
- [ ] 4.7 `deck/cli.py` + 修改 `paulshaclaw/cli.py` 加 `deck` route + `tests/test_psc_cli.py`（含 unknown-command 回歸）

## 5. W4 verify 驗收器（lane，平行）

- [ ] 5.1 `tests/test_deck_verify.py` RED：pass/fail/缺失清單/exit code
- [ ] 5.2 實作 `deck/verify.py`（fnmatch/pathlib 存在性驗收）+ CLI 子命令
- [ ] 5.3 emit 報告掛 verify checklist（翻 auto 前人工程序）

## 6. W5 persona skills 接線（lane，平行）

- [ ] 6.1 `tests/test_persona_skills.py` RED：skills 欄位存續、可選相容、未知 id 僅 warning
- [ ] 6.2 `personas.yaml` 三 role 加 `skills:`；`loader.py`/`contract.py` 讀取並保留欄位（現行丟棄未知欄位需擴充）
- [ ] 6.3 shadow 驗證：card id 存在性查 deck 目錄，缺失 warning 不失敗、不動 guardrail

## 7. W7 整合驗證（整合節點，W1+W3 後）

- [ ] 7.1 整合測試：feature-oneshot 編譯輸出 → `scan_specs` 解析綠、`detect_cycles` 無環、`ready_units` 全 hold 下為空（暫存目錄，不碰活佇列）
- [ ] 7.2 mcu-feature 走同一整合鏈（W2 合流後）
- [ ] 7.3 測試中禁直接 import `paulshaclaw.memory`/`paulshaclaw.lifecycle` 字面（hippo §4.5 清零相容檢查）
- [ ] 7.4 全 repo 測試綠（integration_test_gate）+ policy gate（`python3 -m policy_check --repo .`）

## 8. 收尾

- [ ] 8.1 乾淨環境實走：`psc deck compile feature-oneshot --task <樣例> --emit` → hold specs 落地 → `psc deck verify` checklist 可執行（Phase A DoD）
- [ ] 8.2 README/docs 對齊（R-18）：deck 章節 + `#186` 進度更新
- [ ] 8.3 facade `specs_dir()` 後續提案（開 issue 或併 #91，設計 Open Question 裁決）
