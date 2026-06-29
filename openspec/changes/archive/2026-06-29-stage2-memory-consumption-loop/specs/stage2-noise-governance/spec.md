## ADDED Requirements

### Requirement: 檢索 index 與 brief 對 noise 的 defense-in-depth 排除

`build_index`（`paulshaclaw/memory/moc/search.py`）建立 `retrieval.db` 時、以及 SessionStart slim brief 納入 slice 時，SHALL 對候選 slice 套用既有 `classify_noise`（含 instruction-doc `doc_corpus`，沿用本 spec 既有判準），命中者 MUST NOT 被索引、MUST NOT 進入 brief，使**尚未被 `prune-noise` 清除的殘留噪音**也不會出現在 prompt-retrieval 短清單。此排除為純讀取側、MUST NOT hard-delete 任何檔（刪除仍走既有 `prune-noise` 路徑）。乾淨 slice SHALL 照常索引與檢索。

#### Scenario: 殘留 doc-fragment 不進檢索 index
- **WHEN** knowledge 仍含未經 prune 的 doc-fragment slice，且重建 `retrieval.db`
- **THEN** 該 slice MUST NOT 出現在 `slices_fts`，prompt-retrieval 檢索 MUST NOT 將其列入短清單，且該檔 SHALL 仍存在於 knowledge（未被刪）

#### Scenario: 乾淨 slice 正常索引
- **WHEN** 重建 index 時某 slice 經 `classify_noise` 判為非 noise
- **THEN** 該 slice SHALL 被索引並可被檢索命中

### Requirement: canary/review 類非刪除級池排除

offered pool（檢索 index 與 brief / 短清單）SHALL 排除 canary/smoke fixture 與一次性 PR/adversarial review-record 類 slice（依 `artifact_kind` 或既知標記辨識）。此排除為**池端、非刪除級**：辨識門檻得較 `classify_noise` 寬鬆（因不觸發 hard-delete），且 MUST NOT 刪除該類檔（保留於 knowledge 供稽核）。

#### Scenario: canary fixture 不進短清單但保留在 knowledge
- **WHEN** knowledge 含一個 canary/smoke fixture slice
- **THEN** prompt-retrieval 短清單與 brief MUST NOT 列入該 slice，且該檔 SHALL 仍保留在 knowledge 層

#### Scenario: review-record 不進短清單
- **WHEN** knowledge 含一筆一次性 PR review-record slice
- **THEN** 檢索/短清單 MUST NOT 將其列出
