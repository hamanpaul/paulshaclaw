## Why

2026-07-05 線上評估（#197）：Stage 2 記憶鏈整體健康，但三缺口使其效用打折——retrieval 索引半盲（166/344，兩大專案桶 ~65% 真知識被 broad corpus 誤排除）、janitor reactivation 被 import ledger 單一壞行整段中止、LLM promote park 地板（#185 已 close 但線上仍 6 session parked）。

## What Changes

- Gap ①：`build_index` 噪音排除改 per-project scoped corpus（用既有 `corpus_for_roots()` 接 `projects.yaml` roots；查無 roots → 空 corpus 不排除）；新增 per-project exclude_rate 遙測，>40% WARN（no silent caps）。
- Gap ③：import ledger 逐行容錯——壞行 skip+計數（warning 報 skipped N），不再 abort；ops 清 live 壞行（先備份）。
- Gap ②：先 ops 複驗（6 parked session 快取時間戳 vs #190 merge 時點；殘留 → 清快取+reset budget 交背景 loop 重試；**禁手動 dream run**）；僅當新碼仍失敗才做 parser prose 容忍抽取（唯一頂層 array 才取，歧義 fail-closed）+ prompt 加固。
- 交付形態：3 個獨立 PR 可平行（worker 各自 worktree）。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `stage2-memory-prompt-retrieval`: 索引建構的噪音排除改 per-project scoped corpus，並新增排除率遙測 WARN 要求。
- `stage2-memory-governance`: janitor 讀取 import ledger 須逐行容錯，壞行不得中止 reactivation 掃描。
- `stage2-llm-distillation`: promote 輸出解析新增「散文包裹單一 JSON array」容忍抽取（fail-closed 邊界不變）。

## Impact

- 受影響碼：`paulshaclaw/memory/`（build_index／janitor ledger 讀取／llm_output parser、atomizer prompt）。
- 資料：retrieval.db 需 rebuild（檢索側，knowledge 檔零觸碰、可逆）；runtime cache ops 前備份。
- 遙測：index build 輸出新增 per-project indexed/excluded/exclude_rate。
