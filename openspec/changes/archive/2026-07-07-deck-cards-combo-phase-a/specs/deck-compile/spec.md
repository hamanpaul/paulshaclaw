# deck-compile

## ADDED Requirements

### Requirement: headless 卡編譯為 slice specs、interactive 卡編為前置 checklist
`deck compile` SHALL 僅為 `type: headless` 卡片產生 slice spec 檔（`slice_id = <task-slug>-<card-id>`，frontmatter 含 `dispatch`/`slice_id`/`plan`/`depends_on`）；`type: interactive` 卡片 MUST 編為前置 checklist 輸出於編譯報告，其 `produces` 作為首個 headless slice 的 `plan` 參照與 requires 來源。

#### Scenario: 混合 combo 編譯
- **WHEN** 編譯含 3 張 interactive 卡與 2 張 headless 卡的 combo
- **THEN** 產生恰 2 份 slice spec，編譯報告列出 3 項前置 checklist

#### Scenario: slice_group 合併
- **WHEN** combo 內連續 3 張 headless 卡宣告同一 `slice_group: build`
- **THEN** 三卡合併為單一 slice（`slice_id = <task-slug>-build`），produces 取聯集、depends_on 取聯集

#### Scenario: 未標 slice_group 的 headless 卡隱式串鏈
- **WHEN** headless 卡（或合併後的 slice）未宣告 `depends_on`
- **THEN** 其 slice 隱式依賴前一個 headless slice（保序），首個 headless slice 無依賴

### Requirement: 預設 dry-run 與 emit 安全語意
`deck compile` 預設 SHALL 為 dry-run（僅輸出至 stdout，不寫任何檔案）；`--out <dir>` 寫指定目錄；`--emit` 才寫入活佇列，且 emitted spec 的 `dispatch:` MUST 一律為 `hold`。

#### Scenario: 預設不落地
- **WHEN** 執行 `deck compile` 未帶 `--out`/`--emit`
- **THEN** 檔案系統無任何新增檔案，編譯結果完整印出

#### Scenario: emit 一律 hold
- **WHEN** 帶 `--emit` 編譯任何 combo
- **THEN** 所有產出 spec 的 frontmatter `dispatch` 值為 `hold`

### Requirement: emit 冪等性與檔名
emit SHALL 以 flat 檔名 `<slice_id>.md` 寫入（不建子目錄，因 `scan_specs` 為單層非遞迴掃描）；目標檔已存在時 MUST 預設拒絕並報錯（防覆蓋 in-flight slice），僅 `--force` 時原子覆蓋。

#### Scenario: 同名 spec 已存在時拒絕
- **WHEN** `--emit` 目標目錄已有同名 `<slice_id>.md`
- **THEN** 編譯以非零 exit code 失敗並列出衝突檔案，不覆蓋任何檔

#### Scenario: --force 原子覆蓋
- **WHEN** 帶 `--emit --force` 且同名檔存在
- **THEN** 以 temp+rename 原子覆蓋該檔

### Requirement: specs 目錄解析鏡射 manager 契約
emit 目標目錄 SHALL 以單一 deck 內部 helper 解析，優先序 MUST 與 manager 現行契約一致：`PSC_MANAGER_SPECS_DIR` 環境變數 → `~/.agents/specs`；並 SHALL 有回歸測試斷言與 `manager_daemon` 預設相等。

#### Scenario: env 覆寫生效
- **WHEN** 設定 `PSC_MANAGER_SPECS_DIR=/tmp/x` 並 `--emit`
- **THEN** spec 寫入 `/tmp/x`

### Requirement: additive 與排他規則
`--with <card>` SHALL 把指定卡併入手牌且不取代 combo 骨幹；插入位置優先採顯式 `:after=<id>`/`:before=<id>`，未指定時僅在保守 pattern 覆蓋檢查可證明時自動插入，無法證明 MUST fail-closed 要求明示位置。`--only <card>...` 才是排他模式。

#### Scenario: 顯式定位插入
- **WHEN** `--with atomize:after=code-review`
- **THEN** atomize 卡插入於 code-review 之後，骨幹卡片全數保留

#### Scenario: 無法推斷位置時 fail-closed
- **WHEN** `--with` 卡片未帶定位且其 requires 無法被任一上游 produces pattern 覆蓋證明
- **THEN** 編譯失敗並提示需 `:after=`/`:before=` 明示位置

### Requirement: requires 覆蓋檢查與 external input
編譯期 SHALL 做 pattern-level 檢查（非檔案存在性）：每張卡 `requires` glob 須被上游卡（含 `--with` 併入卡）`produces` pattern 覆蓋；未覆蓋者列為 external input，MUST 要求 `--allow-external` 明示放行，否則報錯不產檔。

#### Scenario: 未放行的外部輸入擋下編譯
- **WHEN** 某卡 requires 無上游 produces 覆蓋且未帶 `--allow-external`
- **THEN** 編譯失敗並列出缺口清單

### Requirement: 佔位符代入與 slug 正規化
`<task-slug>` SHALL 由 `--task` 正規化產生（限 `[a-z0-9-]`、長度 ≤ 60、branch-safe）；卡片使用 `<change>` 而未提供 `--change` MUST 報錯。

#### Scenario: 缺 --change 報錯
- **WHEN** combo 內任一卡 glob 含 `<change>` 且命令未帶 `--change`
- **THEN** 編譯失敗並指出需要 `--change`

### Requirement: parse-level 整合驗收
以實戰卡片資料編譯的輸出 SHALL 通過 coordinator 解析鏈驗收：`scan_specs` 可解析、`detect_cycles` 無環、`ready_units` 於全 hold 下為空集合（不誤觸發自動派工）。

#### Scenario: 整合 dry-run 全綠
- **WHEN** 將 feature-oneshot 編譯輸出置於暫存 specs 目錄並執行解析鏈
- **THEN** 解析成功、無環、ready 集為空
