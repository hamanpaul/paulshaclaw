## 1. 純函式基座（usage.py）

- [ ] 1.1 寫測試：`to_fts_query` 對含 FTS5 特殊字元（`"`/`*`/`(`/`-`/`AND`）的 prompt 產生不致 `OperationalError` 的查詢；空/純標點回空字串
- [ ] 1.2 實作 `to_fts_query(prompt)`（抽 alnum/CJK token、OR 連接、純函式）
- [ ] 1.3 寫測試：`extract_offered` 仍可運作；新增「cited/matched 不再為 used 主訊號」之 deprecation 標記（docstring/註記）
- [ ] 1.4 將 `extract_cited`/`extract_matched` 標為 deprecated（保留向後相容、不再被 used 路徑呼叫）

## 2. prompt-retrieval hook（檢索→短清單→offered）

- [ ] 2.1 寫測試：給假 `retrieval.db` + project + prompt → 產出 ≤k 短清單（標題·一行摘要·絕對路徑）、含 Read 提示；trivial/無命中/`_unknown`/缺 index → 不注入
- [ ] 2.2 寫測試：offered 記錄落地（ledger `offered.jsonl` 含 `{sl_id,path}`）+ per-session `sl_id↔path` 映射累積；未注入則不記
- [ ] 2.3 實作共用 `hooks/_shortlist_common.py`：resolve_project → `to_fts_query` → `search.search()` → relevance gate（有命中 + score 門檻、k=3 上限 5）→ 解析每命中之絕對路徑與一行摘要（重用 builder 摘要邏輯）→ 組短清單 + offered 記錄/映射
- [ ] 2.4 實作 `hooks/claude_user_prompt_submit.py`：讀 UserPromptSubmit payload（prompt/cwd/session_id）→ 呼叫共用邏輯 → 輸出 `hookSpecificOutput.additionalContext`；best-effort、exit 0
- [ ] 2.5 視需要擴 `search.search()` 回傳絕對路徑（或於共用層由 sl_id 反查 path）

## 3. read-attribution hook（PostToolUse Read = used）

- [ ] 3.1 寫測試：Read 被 offered 的 knowledge 路徑 → used 事件 `source:"read",offered:true`；Read 非 offered knowledge → `offered:false`；Read 非 knowledge → 無事件；rename 後以 sl_id 回退仍歸因；任一錯誤 → 不寫、exit 0
- [ ] 3.2 實作 `hooks/claude_post_tool_use.py`：解析 `tool_input.file_path` → realpath under `knowledge/` 判定 → 載入 session offered 映射（path 優先、sl_id 回退）→ append `memory_usage.jsonl` used 事件；best-effort

## 4. 池端/index 噪音排除（重用 classify_noise）

- [ ] 4.1 寫測試：`build_index` 對 `classify_noise` 命中者（doc-fragment/structural/empty）不索引、且不刪檔；乾淨 slice 正常索引
- [ ] 4.2 實作 `build_index`（`search.py`）納入前套 `classify_noise`（含 doc_corpus）排除；確認不影響 hourly dream 主流程
- [ ] 4.3 寫測試：canary-fixture / review-record 依 `artifact_kind`/標記被池端排除（不進 index/短清單）、且保留在 knowledge
- [ ] 4.4 實作 canary/review 非刪除級池排除（index 與 brief 共用辨識）

## 5. SessionStart brief 瘦身

- [ ] 5.1 寫測試：可解析 project → brief 為極簡 orientation（含 note count + per-prompt/Read 提示）、不含 project MOC dump、不含 16-hex 引用前言；無 project/空 → 空 context
- [ ] 5.2 改 `_wakeup_common.py`/`builder.py`：產極簡 orientation；移除 `CITATION_PREAMBLE`；SessionStart 不再寫 session-wide offered 集

## 6. 遙測整併（read-based）

- [ ] 6.1 寫測試：`psc memory usage` 由 `memory_usage.jsonl` 聚出 per-slice `offered_count/read_count/last_read`、never-read 彙總；wakeup 檔不存在仍正確
- [ ] 6.2 改 `usage_ledger.py`：退役 SessionEnd cited/matched used 寫入（offered 改由 §2、used 改由 §3）
- [ ] 6.3 改 `cli.py` usage 子命令為 read-based 聚合

## 7. 部署接線

- [ ] 7.1 `~/.claude/settings.json` 增掛 UserPromptSubmit memory hook（與 `codegraph prompt-hook` 並存於 list）+ PostToolUse matcher `Read` 的 memory hook
- [ ] 7.2 `hooks/install.sh` 納入兩個新 hook，重新同步到 `~/.agents/memory/hooks/`（複製非 symlink）

## 8. 驗證與回歸

- [ ] 8.1 `python3 -m pytest paulshaclaw/memory/tests/` 全綠（含新測試、守住既有 747）
- [ ] 8.2 端到端手測：相關 prompt → 短清單出現（含絕對路徑）→ Read 該路徑 → `memory_usage.jsonl` 有 `source:"read",offered:true` 事件；trivial prompt 不注入
- [ ] 8.3 確認 hourly dream/atomize/janitor/MOC 主流程未受影響（回歸）

## 9. 現存噪音 prune（操作面、gated、destructive）

- [ ] 9.1 備份 `~/.agents/memory/knowledge/`
- [ ] 9.2 `psc memory knowledge prune-noise --project <repo> --dry-run` → 人核 manifest（數字超預估即停下問）
- [ ] 9.3 確認後 `--apply` 清除殘留 doc-fragment + 空 session-metadata，重建 MOC/index 並驗證短清單不再含噪音
