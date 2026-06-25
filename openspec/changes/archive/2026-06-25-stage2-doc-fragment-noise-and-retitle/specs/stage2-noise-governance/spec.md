# stage2-noise-governance

classifier 新增 `doc-fragment`（corpus 逐字比對）類別，產生端與 prune 共用 instruction-doc 語料。

## ADDED Requirements

### Requirement: 以 instruction 文件逐字語料判定 doc-fragment

系統 SHALL 擴充 `classify_noise(frontmatter, body)`，新增選用參數 `doc_corpus`（agent-instruction 文件——CLAUDE.md / AGENTS.md / GEMINI.md——的逐字參照語料，含 heading 集合與內容行集合）。當提供非空 `doc_corpus` 時，若 body strip 後第一行為 markdown heading 且其 heading 文字逐字命中語料 heading 集合，**且** body 去標題後 ≥2 條內容行逐字命中語料行集合，則判為 noise、`reason` 為 `doc-fragment`。判定 SHALL 為逐字（normalized whitespace）比對（deletion-grade，只命中可證實為 instruction 文件片段者），MUST NOT 僅憑「heading 為編號章節」此單一結構特徵判定。未提供 `doc_corpus`（或語料為空）時，doc-fragment 規則 SHALL 不啟用，既有判定行為不變。

#### Scenario: instruction 文件編號章節碎片判為 doc-fragment

- **WHEN** slice body 第一行為 `## 6. 自主維護規則（agent-managed）` 等 instruction 文件章節 heading，後續 ≥2 內容行為該文件逐字內容，且提供涵蓋該文件的 `doc_corpus`
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `doc-fragment`

#### Scenario: instruction 文件非編號段落碎片亦判為 doc-fragment

- **WHEN** slice body 第一行為 `## 動工前` 等 AGENTS.md 段落 heading，後續內容行逐字命中語料，且提供對應 `doc_corpus`
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `doc-fragment`

#### Scenario: 真知識的編號小節不被誤刪

- **WHEN** slice body 第一行為 `## 1. 背景` 等編號 heading，但內容為原創知識、未逐字命中任何 instruction 語料
- **THEN** `classify_noise` SHALL 回 `is_noise=False`（編號章節單一特徵 MUST NOT 致刪）

#### Scenario: 未提供語料時規則惰性

- **WHEN** 呼叫 `classify_noise(fm, body)` 未傳 `doc_corpus`（或語料為空），body 為任意 doc 碎片
- **THEN** doc-fragment 規則 SHALL 不啟用，回傳結果與既有（structural-echo / placeholder / empty）判定一致

### Requirement: 產生端與回溯 prune 共用 doc-fragment 判準

atomize 的 promote pass 與 `psc memory knowledge prune-noise` SHALL 自 instruction-doc 語料來源組裝 `doc_corpus` 並傳入 `classify_noise`，使 doc-fragment 於產生端被阻斷新生、於回溯 prune 被清除。語料探測 SHALL 邊界化（限定安全 root、限深、skip 重目錄），探測不到語料時 doc-fragment 規則惰性而不致誤刪。

#### Scenario: 回溯 prune 清除 doc-fragment

- **WHEN** 對含 instruction 文件碎片與真知識的 knowledge 執行 `prune-noise --apply`，且語料涵蓋該 instruction 文件
- **THEN** doc-fragment 碎片 SHALL 被 hard delete、真知識 SHALL 全數保留、manifest SHALL 記錄每筆刪除（reason `doc-fragment`）、MOC SHALL 重建且不含已刪 slice

#### Scenario: 產生端阻斷 doc-fragment 新生

- **WHEN** promoter 對某 session 產出一個 body 為 instruction 文件逐字章節的 slice，且產生端已組裝涵蓋該文件的語料
- **THEN** 該 slice MUST NOT 寫入 knowledge 層、SHALL 計入 `noise_dropped`，source fragment SHALL 仍被 archive
