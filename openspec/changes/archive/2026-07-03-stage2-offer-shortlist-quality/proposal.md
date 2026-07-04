## Why

audit wf_2bd0b606-6e4 的 offer-read-conversion 項（verdict=CONFIRMED）查明 offered→read 轉換率低（unique 10.6% / session 18.5%）的三個主因，對應 issue #178：

1. **候選池品質**：generic 標題 artifact（`report-*` / `task-*` / `todo-*` / `overview` / `problem` / `untitled` / `review-summary`）佔 offer impressions 49~55%，且從未被 read；OR-join bm25（`retrieval.py:48` 全 token OR、`moc/search.py:110` `bm25 - 0.1*link_weight`）為 recall 導向，body 長、詞頻高的 artifact 常態霸佔 top-3（doc-alignment 雙胞胎 53x+49x 同佔 2/3 格）。
2. **重複轟炸**：每個 user prompt 重注入且無 session 內去重——`hooks/_shortlist_common.py` 的 offered map（`runtime/wakeup/<tool>__<sid>.offered.json`，`_record_offered` 已維護）只寫不讀回；同 session 同一筆最多 offer 32 次、120/301 events 是重複組合，分母灌水且模型學會忽略 shortlist。
3. **注入行零資訊**：`_summary`（`_shortlist_common.py:16-31`）取首個 body 行，常等於標題重複（「[overview] — Overview」），模型無從判斷開檔價值；被 read 的 11 筆中 8 筆是具體事件式標題。

次要因素（read 偵測只認 Read 工具、Bash grep 直讀漏記 2 次）屬使用者 settings（PostToolUse matcher），不入本 change（見 design Ops 邊界）。

## What Changes

- `paulshaclaw/memory/noise.py`：新增 title 級純函式 `is_generic_title(title)`（frozenset + prefix regex），並在 `pool_exclude_reason`（:202）加 `generic-title` 排除規則——generic 標題 slice 不進檢索池（非刪除級，檔案保留；retitle 後可回池）。取捨（vs `moc/search.py` link_weight 重罰）記錄於 design.md。
- `paulshaclaw/memory/hooks/_shortlist_common.py`：`build_shortlist_and_record` 讀回 per-session offered map（`by_id`），過濾本 session 已 offer 的 sl_id；檢索端過取候選（`SHORTLIST_FETCH_K`）使過濾後仍能以次佳補位至 k；全數已 offer 則不注入、不記錄。
- `paulshaclaw/memory/hooks/_shortlist_common.py`：`_summary(path, title)` 跳過與 title 正規化後相同的行，改取下一個有資訊行；全部為標題重複時摘要為空字串。
- `paulshaclaw/memory/retitle.py`：掃描條件由 `untitled` 擴到 generic 標題清單（共用 `noise.is_generic_title` 單一真相源），使 generic artifact 可被重生具體標題後回到檢索池。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `stage2-noise-governance`：新增「generic 標題 artifact 之非刪除級池排除」requirement（`is_generic_title` + `pool_exclude_reason` 之 `generic-title`）。
- `stage2-memory-prompt-retrieval`：新增「session 內去重」與「短清單摘要行資訊量」兩條 requirement。
- `stage2-knowledge-retitle`：修改「untitled 真知識 slice 標題重生與重命名」requirement，掃描範圍擴及 generic 標題。

## Impact

- Affected code：`paulshaclaw/memory/noise.py`（`pool_exclude_reason` + 檔尾新增區塊）、`paulshaclaw/memory/hooks/_shortlist_common.py`、`paulshaclaw/memory/retitle.py`。`moc/search.py` **不改**（既有 `pool_exclude_reason` 呼叫點 :71 自動生效）。
- Affected tests：`paulshaclaw/memory/tests/test_noise.py`、`test_moc_search.py`、`test_shortlist_common.py`、`test_retitle.py`（皆為新增測試，不改既有案例）。
- Deployment：`hooks/_shortlist_common.py` 由 `install.sh` 複製部署至 `~/.agents/memory/hooks/`，merge 後須重跑 `install.sh`（git pull 不等於部署）；現存 index 中的 generic slice 要等下次 index 重建才出池。皆記於 plan 的 Deployment/Ops notes。
- 併行衝突控制：#177 亦動 memory 模組（rekey/prune 清單模式），本 change 對 `noise.py` 的新增置於檔尾獨立區塊、`pool_exclude_reason` 僅單一插入點，diff 區塊不重疊。
- Non-Goals：不動 bm25 ranking 與 `to_fts_query`、不做跨 session 冷卻、不改 read 歸因（PostToolUse Bash matcher 屬使用者 settings）、不刪任何 knowledge 檔、不執行 live retitle/index 重建（ops 另議）。
