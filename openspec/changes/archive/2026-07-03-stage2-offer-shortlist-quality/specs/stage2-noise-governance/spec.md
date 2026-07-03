## ADDED Requirements

### Requirement: generic 標題 artifact 之非刪除級池排除

系統 SHALL 提供 title 級純函式 `is_generic_title(title)`：將 title 正規化（小寫、空白與底線折成 `-`）後，恰為 `overview` / `problem` / `untitled` / `review-summary` / `report` / `task` / `todo`，或以 `report-` / `task-` / `todo-` 為字首者，判為 generic 標題（session 產物型標籤、非知識原子）。`pool_exclude_reason(frontmatter)` SHALL 於 `atom_title` 或 `title` 命中 generic 標題時回傳 `generic-title`，使該 slice 於 `build_index` 重建檢索池時被排除（不進 offered pool / 短清單）。此排除為**池端、非刪除級**：MUST NOT 刪除或修改該檔（保留於 knowledge，供 retitle 重生標題後回池）。`session_title` 為 generic MUST NOT 觸發排除（session 標題非 slice 標題）。僅「包含」generic 詞而非恰為或字首命中者（如 `overview-of-uart-pinmux`、`problem-with-dma-burst`）MUST NOT 判為 generic。空字串或缺失 title MUST NOT 判為 generic（留給既有 untitled/retitle 治理）。

#### Scenario: generic 標題 slice 不進檢索 index

- **WHEN** knowledge 含一筆 `title: report-testpilot` 的 slice 與一筆具體標題的 slice，且重建 `retrieval.db`
- **THEN** generic slice MUST NOT 出現在 `slices_fts`（檢索 MUST NOT 命中），具體標題 slice SHALL 照常索引，且 generic 檔 SHALL 仍存在於 knowledge（未被刪除或修改）

#### Scenario: 恰為 generic 名稱者命中、僅包含者不命中

- **WHEN** 以 `overview`、`Review Summary`、`todo_cleanup`、`task-cockpit-swap` 呼叫 `is_generic_title`
- **THEN** 回傳值 SHALL 皆為 True
- **WHEN** 以 `overview-of-uart-pinmux`、`problem-with-dma-burst`、`單一-com0-死因未解`、空字串呼叫 `is_generic_title`
- **THEN** 回傳值 SHALL 皆為 False

#### Scenario: session_title generic 不致排除

- **WHEN** 某 slice 的 `title` 為具體標題、`session_title` 為 `report-testpilot`
- **THEN** `pool_exclude_reason` SHALL 回傳 None（該 slice 照常入池）

#### Scenario: retitle 後回池

- **WHEN** 某 generic 標題 slice 經 retitle 重生為具體標題，且之後重建 `retrieval.db`
- **THEN** 該 slice SHALL 重新被索引並可被檢索命中
