# deck-verify

## ADDED Requirements

### Requirement: 卡片 produces 存在性驗收
`deck verify <card-id> --task-slug <slug> [--root <dir>]` SHALL 對單張卡的 `produces` glob 做存在性驗收（佔位符代入後 fnmatch/pathlib 比對），回報 pass/fail 與缺失清單，exit code MUST 反映結果（0=pass、非 0=fail）供 CI/gate 使用。Phase A 僅驗存在性，不驗內容。

#### Scenario: 產出齊備
- **WHEN** 卡片所有 produces glob 於 `--root` 下均有匹配檔案
- **THEN** 回報 pass 且 exit code 0

#### Scenario: 產出缺失
- **WHEN** 任一 produces glob 無匹配
- **THEN** 回報 fail、列出缺失 glob 清單、exit code 非 0

### Requirement: 翻牌前人工 checklist 約定
編譯報告 SHALL 印出「翻 `auto` 前先跑 `deck verify`」的 checklist（Phase A 為作業紀律，機器強制 gate 屬 Phase B 非目標）。

#### Scenario: emit 報告含 verify checklist
- **WHEN** `--emit` 成功產出 specs
- **THEN** 報告列出各前置卡對應的 `deck verify` 命令
