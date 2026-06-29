## ADDED Requirements

### Requirement: 任務條件式短清單注入（UserPromptSubmit）

memory prompt-retrieval hook SHALL 於 UserPromptSubmit 解析 session 的 project、由當前 prompt 建構 FTS 查詢、對該 project 跑既有 bm25 檢索（`search.py`）、套用 relevance gate，並將 top-k（預設 k=3、上限 5）結果以**短清單**注入為 additional context：每列為「標題 · 一行摘要 · 該 slice 的絕對路徑」，並附「相關項用 Read 開啟路徑取全文」提示。hook SHALL 為 best-effort：project 無法解析、index 不存在、無命中或任何例外時，MUST NOT 注入、MUST NOT 阻斷或干擾 prompt，且 exit 0。

#### Scenario: 相關 prompt 產生短清單
- **WHEN** 在可解析 project 的 session 送出與某些 knowledge slice 相關的 prompt，且檢索有過 gate 的命中
- **THEN** hook SHALL 注入 ≤k 列短清單，每列含標題、一行摘要與該 slice 的絕對路徑，並含 Read 提示

#### Scenario: trivial 或無命中 prompt 不注入
- **WHEN** prompt 經 `to_fts_query` 後為空（如 `/effort`、純標點）或檢索無過 gate 命中
- **THEN** hook MUST NOT 注入任何短清單，prompt 照常進行

#### Scenario: 未知 project 或 index 缺失不注入
- **WHEN** cwd 解析為 `_unknown`，或 `retrieval.db` 不存在
- **THEN** hook MUST NOT 注入，且 exit 0

#### Scenario: 任一錯誤不干擾 prompt
- **WHEN** 檢索或注入過程發生任何例外
- **THEN** hook SHALL log warning、不注入、exit 0，prompt 不受影響

### Requirement: FTS 查詢淨化純函式

系統 SHALL 提供純函式 `to_fts_query(prompt)`，自任意 prompt 文字抽出 alnum/CJK token 並以 OR 連接成合法 FTS5 查詢，使任意 prompt（含 FTS5 特殊字元 `"`、`*`、`(`、`-` 等）MUST NOT 觸發 FTS5 語法錯誤。空字串或無可用 token 時 SHALL 回空字串（由呼叫端視為不檢索）。函式 MUST 為純函式、不丟例外。

#### Scenario: 特殊字元被淨化不致語法錯誤
- **WHEN** 對含 `"`、`*`、`(`、`AND` 等 FTS5 敏感字元的 prompt 呼叫 `to_fts_query`
- **THEN** 回傳的查詢字串用於 `slices_fts MATCH ?` MUST NOT 引發 `sqlite3.OperationalError`

#### Scenario: 空或無 token 回空
- **WHEN** prompt 為空白或僅標點
- **THEN** `to_fts_query` SHALL 回空字串

### Requirement: per-prompt 記錄 offered 與對齊映射

對每次注入的短清單，hook SHALL append 一筆 offered 記錄至持久 ledger（含 `session_id`、`project`、`ts`、`offered`=該批 `{sl_id, path}` 陣列），並維護 per-session 的 `sl_id ↔ 絕對路徑` 雙向映射（`runtime/wakeup/<tool>__<sid>.offered.json`，跨本 session 多次 prompt 累積），供 read 歸因對齊。寫入失敗 MUST NOT 影響注入或 prompt（best-effort）。

#### Scenario: offered 落地含 id 與路徑
- **WHEN** 某次 UserPromptSubmit 注入了短清單
- **THEN** ledger SHALL 新增一筆含該批 `{sl_id, path}` 的 offered 記錄，且 per-session 映射 SHALL 含各 sl_id↔path

#### Scenario: 未注入則不記 offered
- **WHEN** 該 prompt 未注入短清單（無命中／未知 project）
- **THEN** MUST NOT 寫 offered 記錄
