## Context

Stage 2 memory 的 offer 面（UserPromptSubmit 短清單注入）已於 change `stage2-memory-consumption-loop` 上線：`hooks/_shortlist_common.py` 對每個非 slash prompt 跑 bm25 檢索、注入 top-3、記 offered ledger 與 per-session offered map。audit wf_2bd0b606-6e4（offer-read-conversion，CONFIRMED）以 302 events / 818 impressions 的 ledger 重算證實三個主因：generic 標題 artifact 佔近半 impressions 且零 read、同 session 無去重（同筆最多 32 次）、注入摘要行常為標題重複。本 change 對應 issue #178，與 #148（消費端可觀測性）互補：#148 管量測，本 change 管供給品質。

程式碼錨點（實作前先讀）：

- `paulshaclaw/memory/noise.py:202-216` `pool_exclude_reason`——既有「非刪除級池排除」choke point（canary/review 已走此路徑）。
- `paulshaclaw/memory/moc/search.py:71` `build_index` 對每檔呼叫 `pool_exclude_reason`，命中即不索引；`:110` 排序為 `bm25 - 0.1*link_weight`。
- `paulshaclaw/memory/hooks/_shortlist_common.py:13` `SHORTLIST_K=3`；`:16-31` `_summary`；`:53-81` `_record_offered`（維護 `runtime/wakeup/<tool>__<sid>.offered.json` 的 `by_path`/`by_id` 雙向映射，只寫不讀）；`:84-115` `build_shortlist_and_record`。
- `paulshaclaw/memory/retitle.py:28-30` `_is_untitled`（現行掃描條件：`title == "untitled"` 或檔名 `untitled--` 前綴）。

## Goals / Non-Goals

**Goals:**

- generic 標題 artifact 不再進入 retrieval pool（offer shortlist 的候選來源），且此排除可逆（retitle 後回池）。
- 同 session 已 offer 過的 slice 不重複注入；重複 prompt 以次佳候選補位，候選枯竭則不注入、不灌水 offered 分母。
- 注入摘要行不再是標題重複；無資訊行時誠實給空摘要，不硬湊。
- retitle 管線可處理 generic 標題（非只 `untitled`），與池排除形成「出池→重生標題→回池」閉環。

**Non-Goals:**

- 不調 bm25 ranking、不加分數 threshold（audit A4：需 read-data 才能調參）。
- 不做跨 session 冷卻或全域 offer 頻率上限。
- 不改 read 歸因（PostToolUse Bash matcher 屬使用者 `~/.claude/settings.json`，不入 PR——見 Ops 邊界）。
- 不刪除任何 knowledge 檔（generic 排除為池端、非刪除級）。
- 不在 PR 內執行 live 的 retitle / index 重建 / prune（ops 動作另議）。

## Decisions

### D1: generic 標題排除走 `pool_exclude_reason`，不走 search 端 link_weight 重罰（二選一之取捨）

issue #178 修法 1 給兩個選項。讀碼後選 `noise.py pool_exclude_reason`，理由：

1. **侵入性最小**：`pool_exclude_reason` 已是 `build_index` 的既有排除 choke point（`moc/search.py:71`），且「frontmatter 級、非刪除級」語意已建立（canary/review 同路徑）；本方案只在 `noise.py` 加一個 title 判定函式與一條 return 分支，`moc/search.py` 完全不用改。
2. **link_weight 重罰不可控**：現行排序 `bm25 - 0.1*link_weight` 中 bm25 原始分量級隨 query 長度浮動（`retrieval.py:10-13` 註解自承 threshold tuning deferred、缺 read-data）；generic 筆記 body 長、詞頻高，bm25 常大幅領先，線性小罰壓不住 top-3，罰多重才夠無資料可調。「沉底」的實效不確定，而「出池」是確定性行為、可直接測試。
3. **可逆性**：出池不是刪除。retitle（D4）重生具體標題後，下次 `build_index`（dream moc pass）自然回池。

判定規則保守、僅收 issue 明列清單：正規化（小寫、空白/底線折 `-`）後 **恰為** `overview` / `problem` / `untitled` / `review-summary` / `report` / `task` / `todo`，或 **字首** `report-` / `task-` / `todo-`。僅「包含」generic 詞者（`overview-of-uart-pinmux`、`problem-with-dma`）不命中，避免誤傷具體標題。`session_title` 不參與判定（session 標題 generic 不代表 slice generic；audit 中被 read 的具體 slice 常掛在 generic session 下）。曾考慮把 audit top offender「doc-alignment-review-pr-review」納入（如 `-review` 後綴規則），因會誤傷「code-review 工作流」類真知識而否決——該類 review-record 由既有 `artifact_kind: review` 排除與本 change 的 session 內去重（D2）雙重緩解。

### D2: session 內去重讀回既有 offered map，不新增持久化狀態

`_record_offered` 已維護 `runtime/wakeup/<tool>__<sid>.offered.json`（`by_id`: sl_id→path）。去重即「注入前讀回 `by_id` 鍵集合，過濾命中者」——零新檔案格式、零 schema 遷移。配套決策：

- **過取補位**：檢索 `limit` 由 `SHORTLIST_K`(3) 改 `SHORTLIST_FETCH_K`(12)，過濾後取前 K——否則重複 prompt 只會「注入變少→變無」，而非輪替出次佳候選。12 = 4 倍 K，涵蓋 audit 觀測的同 session 重複規模，且 FTS 查詢成本不變（同一次 query，只是 LIMIT 放大）。
- **fail-open**：map 缺失/損毀時視為空集合照常 offer（寧可重複、不可因讀檔失敗完全靜默）；與 shortlist 整體 best-effort 語意一致。對比：redaction 是 fail-closed（安全性質不同）。
- **全數已 offer**：回空字串、不注入、不追加 offered 記錄（維持既有「未注入不記錄」不變量，`test_shortlist_common.py` 已鎖此語意）。
- 寫入端 `_record_offered` 的 map 路徑抽成 `_offered_map_path` 供讀寫兩端共用，防路徑 drift。

### D3: 摘要行「近同」以正規化比對，全 echo 時給空摘要

`_summary(path)` 改為 `_summary(path, title)`：逐行掃描時跳過「正規化後與 title 相同」的行（正規化 = 小寫 + 去除所有非 word 字元，故 `Overview` ≈ `overview`、`Review Summary` ≈ `review-summary`）。全部行皆為 title echo 時回 `""`——`format_shortlist` 對空 summary 輸出 `- [title] —  — path`，誠實呈現「無摘要」而非硬塞重複資訊。不做語意近似（embedding）比對——超出最小 diff，且正規化比對已覆蓋 audit 觀測的全部 echo 樣態。

### D4: retitle 掃描擴充共用 `is_generic_title` 單一真相源

`retitle.py::_is_untitled` 追加 `or is_generic_title(title)`，直接 import `noise.is_generic_title`——池排除與 retitle 掃描用同一個判定，清單改動永遠同步。既有防護不變：doc-fragment guard（`classify_noise` 命中即 skip 留給 prune-noise）、distill 失敗 skip、預設 dry-run、manifest 稽核。retitle 是手動 CLI（dream loop 不含 retitle pass），掃描條件放寬不影響常駐路徑。

### D5: 與 #177 的 diff 隔離

#177（rekey 遷移 + prune 固定清單）同批進行、亦動 memory 模組。本 change 對 `noise.py` 的新增全部置於**檔尾獨立區塊**（`_GENERIC_EXACT_TITLES` / `_GENERIC_TITLE_PREFIX` / `is_generic_title`），`pool_exclude_reason` 內僅單一插入點（`return None` 前加一個 if）；不動 `classify_noise`、不動 `cli.py`。兩票規則各自獨立，merge 衝突面最小。

## Risks / Trade-offs

- **generic 清單誤傷**：某真知識恰好標題為 `overview`——緩解：排除非刪除級（檔案保留）、retitle 可重生標題回池、清單保守僅 issue 明列項、prefix 僅 `report-`/`task-`/`todo-` 三個。
- **去重使重複 prompt 枯竭後不注入**：設計如此（audit 證實第一次沒讀之後的重複注入不產生 read，只灌水分母）；新 session 重新起算。
- **`SHORTLIST_FETCH_K` 放大檢索行數**：LIMIT 12 vs 3，對 FTS 查詢成本可忽略（同一 MATCH，排序後切片）。
- **hooks 部署落差**：`_shortlist_common.py` 由 `install.sh` 複製部署（`install.sh:171` 清單已含此檔）；merge 後未重跑 `install.sh` 時部署副本 stale。緩解：plan 的 Deployment notes 明列步驟。
- **存量 index 未即時出池**：`generic-title` 排除在下次 `build_index`（dream moc pass 每小時）才生效——可接受，或 ops 手動觸發（不入 PR）。

## Migration Plan

無資料遷移。行為變更隨 index 重建與 hooks 重新部署漸進生效；rollback = revert PR + 重跑 `install.sh` + 重建 index。live 的 retitle 執行（對現存 generic 標題 slice 重生標題）為 ops 動作，工具就緒後以 `--dry-run` 核 manifest 再 `--apply`，不屬本 change 交付。

## Open Questions

1. `doc-alignment-review-pr-review` 雙胞胎（近重複 promote）是否需要 atomizer 端去重治理——audit open question，另案處理，本 change 僅以 session 內去重緩解其轟炸。
2. generic 清單未來是否需要 config 化（`atomizer.yaml` 或獨立 config）——目前 hardcode frozenset 已滿足，等第二個調整需求出現再議。
3. 轉換率指標口徑（event/unique/session 三口徑並列）屬 #148 telemetry 範圍，本 change 不動。
