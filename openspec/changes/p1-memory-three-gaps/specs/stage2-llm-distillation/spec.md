## ADDED Requirements

### Requirement: promote 輸出散文包裹容忍抽取
LLM promote 輸出解析 SHALL 在現行 unwrap 之上支援「散文包裹單一 JSON array」的容忍抽取：當且僅當輸出文字中存在唯一頂層 JSON array 時抽取該 array 續行驗證；多個候選或無候選時維持現行失敗路徑（fail-closed），schema 驗證不放寬。

#### Scenario: 散文包住唯一 array
- **WHEN** 模型輸出為說明文字包裹一個頂層 JSON array
- **THEN** parser 抽出該 array 並按既有 lenient 驗證續行

#### Scenario: 歧義輸出拒絕
- **WHEN** 輸出含兩個以上頂層 JSON array 或完全無 array
- **THEN** 解析失敗走既有 retry/park 路徑，不猜測
