## ADDED Requirements

### Requirement: session 內去重（同 slice 不重複 offer）

prompt-retrieval hook SHALL 於注入前讀回 per-session offered 映射（`runtime/wakeup/<tool>__<sid>.offered.json` 之 `by_id`），過濾本 session 已 offer 過的 `sl_id` 後才注入。檢索端 SHALL 過取候選（fetch 上限 > k），使過濾後仍能以次佳候選補位至 k 筆。過濾後無剩餘候選時 MUST NOT 注入、MUST NOT 追加 offered 記錄（維持「未注入不記錄」不變量，offered 分母不灌水）。映射檔缺失或損毀時 SHALL fail-open（視為空集合、照常 offer），且任何讀取錯誤 MUST NOT 阻斷或干擾 prompt。去重範圍為單一 session：新 session MUST NOT 受先前 session 的 offered 影響。offered 映射的檔案路徑 SHALL 由讀寫兩端共用之單一函式產生（防 drift）。

#### Scenario: 重複 prompt 以次佳補位

- **WHEN** 同 session 先後送出兩個相關 prompt，且第一次已 offer 了最佳候選，池內仍有其他相關候選
- **THEN** 第二次注入 MUST NOT 含第一次已 offer 的 `sl_id`，且 SHALL 以次佳候選補位注入

#### Scenario: 候選枯竭不注入不記錄

- **WHEN** 同 session 再次送出相關 prompt，但所有相關候選皆已 offer 過
- **THEN** hook MUST NOT 注入任何短清單，且 offered ledger 與 per-session 映射 MUST NOT 新增記錄

#### Scenario: 新 session 不受舊 session 去重影響

- **WHEN** 另一個 session 送出相同 prompt
- **THEN** hook SHALL 照常注入該 session 尚未 offer 過的候選

#### Scenario: 映射損毀 fail-open

- **WHEN** per-session offered 映射檔內容非法（無法 parse）
- **THEN** hook SHALL 視為空集合照常注入，MUST NOT 拋出例外或干擾 prompt

### Requirement: 短清單摘要行資訊量（跳過標題重複行）

短清單摘要 SHALL 取 slice body 中第一個「有資訊」行：跳過 YAML frontmatter、空白行，以及正規化後與該 slice `title` 相同之行（正規化 SHALL 忽略大小寫、空白、標點與底線差異，例如 `# Overview` ≈ `overview`、`Review Summary` ≈ `review-summary`）。全部行皆為標題重複（或 body 無可用行）時，摘要 SHALL 為空字串——注入列仍含標題與絕對路徑，MUST NOT 以標題重複行充當摘要。

#### Scenario: 首行為標題重複時取下一個有資訊行

- **WHEN** 某 slice `title` 為 `overview`，body 首行為 `# Overview`、次行為具體技術結論
- **THEN** 注入摘要 SHALL 為該具體技術結論行，MUST NOT 為 `Overview`

#### Scenario: 全部為標題重複時摘要為空

- **WHEN** 某 slice body 僅含與 title 正規化後相同的行
- **THEN** 摘要 SHALL 為空字串，注入列仍含標題與路徑

#### Scenario: 首行非標題重複時行為不變

- **WHEN** 某 slice body 首行為與 title 不同的實質內容
- **THEN** 摘要 SHALL 為該首行（與既有行為一致）
