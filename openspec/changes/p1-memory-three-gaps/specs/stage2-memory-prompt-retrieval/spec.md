## ADDED Requirements

### Requirement: 索引噪音排除採 per-project scoped corpus
`build_index` 的 doc-fragment 噪音排除 SHALL 對每個 project 桶僅使用該 project 自身 instruction roots（依 projects.yaml 映射，經 `corpus_for_roots()`）建構的語料；project 查無 roots 時使用空語料（不排除）。

#### Scenario: 跨 project 不誤排除
- **WHEN** project B 的 slice 內容與 project A 的 instruction 檔逐字重合
- **THEN** B 的 slice 不因 A 的語料被排除於索引之外

#### Scenario: roots 缺席不排除
- **WHEN** 某 project 在 projects.yaml 無 root 映射
- **THEN** 該 project 桶零排除、全數進入索引

### Requirement: 索引排除率遙測
index build SHALL 輸出 per-project `indexed / excluded / exclude_rate`；任一 project 的 exclude_rate 超過 40% 時輸出 WARN（進 build 輸出與 log），不得靜默。

#### Scenario: 排除率超標
- **WHEN** 某 project 桶排除率為 50%
- **THEN** build 輸出含該 project 的 WARN 與具體比率
