# Memory 消費端可觀測性（usage telemetry）設計

> 日期：2026-06-25 ｜ 來源：brainstorming（#148 Option A）
> 前置：記憶採用評估（#139 P2 收尾）發現「注入後 agent 是否真用」是黑盒；本設計做 #148 的 A 案第一刀。

## 1. 背景與問題

三家 agent 的記憶管線雙向都接好（擷取 + wake-up 注入），但**注入後 agent 有沒有讀/用，完全無訊號**。沒有消費端訊號就量不出 ROI、無法調 relevance、decay 缺真實依據。本設計建立**最小 usage 訊號管道**：知道每個 session 被「offered（注入）」了哪些 slice、agent 實際「used（引用/命中）」了哪些。

證據基礎：wake-up brief 含 64 個可 regex 抽的 `sl-[0-9a-f]{16}`；claude SessionEnd payload 有 `transcript_path`（JSONL）可拿 assistant 訊息；現有 hook 結構在 `~/.agents/memory/hooks/`（`_wakeup_common.py` 算 brief、`*_session_end.py` 擷取）。

## 2. 決策（brainstorming 拍板）

| 決策 | 選擇 | 理由 |
|---|---|---|
| used 判準 | **hybrid：cited（顯式 `[[sl-id]]`）+ matched（標題 text-match）分開記** | 引用是強訊號但 agent 未必照做；text-match 補涵蓋率；兩者分開記可分辨可信度。 |
| 範圍 | **claude-only 先行**（offered 三家共用、used 只做 claude） | claude 用最多、`transcript_path` JSONL 最好解析；驗證價值後再擴 codex/copilot。 |
| 引用前言落點 | brief 內（隨記憶注入） | 三家共用、與記憶同生命週期。 |
| 本刀範圍 | 只建資料管線（offered/used ledger + 查詢 CLI） | 接回 relevance/decay 需先有數據，列為後續。 |

## 3. 目標與非目標

**目標**
- 每 session 記錄 offered slice（三家）。
- claude session 記錄 used（cited + matched）。
- CLI 查詢「過去 N 天哪些 slice 被 cited/matched/offered 幾次、最後使用」。

**非目標**
- 接回 brief relevance 排序、janitor decay（後續，需先有數據）。
- codex/copilot 的 used 解析（先只 offered）。
- 強制 agent 引用（只提示，不阻斷）。

## 4. 架構與單元

### ① `paulshaclaw/memory/usage.py`（純函式、無 IO、單一真相源）

```python
extract_offered(brief: str) -> list[tuple[str, str]]
    # 從 brief 的 [[stem--sl-id|title]] 抽 (slice_id, title)

extract_cited(assistant_text: str, offered_ids: set[str]) -> set[str]
    # assistant 文字中出現的 [[sl-id]] / 裸 sl-id，且 ∈ offered_ids（強訊號）

extract_matched(assistant_text: str, offered: list[tuple[str, str]]) -> set[str]
    # assistant 文字出現某 offered slice 的 title（title strip 後 ≥ 8 字才比對，
    # 避免如 "spec"/"task" 等短標題巧合誤判）→ matched（弱訊號）
    # cited 已涵蓋者不重複列入 matched
```

判定只吃「assistant 文字」字串（role 過濾由 hook 負責，見③），保持純函式可測。

### ② SessionStart（共用 `_wakeup_common`，三家）

- `compute_brief` 在 brief 前置 **引用前言**（常數）：提示「若參考了下列記憶，請在回覆標註 `[[sl-id]]`」。brief 為空時不加前言。
- 算出 brief 後 `extract_offered` → 原子寫 `runtime/wakeup/<tool>__<sid>.json`：
  ```json
  {"session_id": "...", "tool": "claude-code", "project": "...", "ts": "...",
   "offered": [{"id": "sl-...", "title": "..."}, ...]}
  ```
- offered 寫入失敗只 log、不影響 brief 輸出（best-effort）。

### ③ claude SessionEnd（`claude_session_end.py`，先只 claude）

- 讀 `runtime/wakeup/claude-code__<sid>.json`（offered）；不存在 → 跳過 usage（無 event）。
- 讀 `transcript_path`（payload 提供；若欄位缺或檔不存在 → 跳過 usage）JSONL，**只取 role=assistant 的訊息文字**串接（排除被注入的 brief 本身，避免假陽性）。
- `cited = extract_cited(text, offered_ids)`、`matched = extract_matched(text, offered) - cited`。
- append `runtime/ledger/memory_usage.jsonl`：
  ```json
  {"ts": "...", "session_id": "...", "tool": "claude-code", "project": "...",
   "offered": 64, "cited": ["sl-..."], "matched": ["sl-..."]}
  ```
- 全程 best-effort，沿 #141 韌性：任何錯誤只 log，hook 照常 exit 0、擷取/import 不受影響。

### ④ CLI `psc memory usage`

- `memory usage --memory-root <root> [--since <iso>] [--json]`：聚合 `memory_usage.jsonl` → 每 slice 的 `offered_count / cited_count / matched_count / last_used`，依 cited 降冪。
- 另給彙總：總 session 數、平均每 session cited/matched、從未被 used 的 offered slice 數（給未來 decay 用）。

### ⑤ 資料流

```
SessionStart → compute_brief[+前言] → runtime/wakeup/<tool>__<sid>.json{offered}     (三家)
SessionEnd(claude) → offered + transcript(assistant only) → cited + matched
                   → runtime/ledger/memory_usage.jsonl
CLI: memory usage → 聚合報告（per-slice + 彙總）
```

## 5. 錯誤處理

- 所有 hook 路徑 best-effort：缺 offered 檔 / 缺 transcript / 解析失敗 → 跳過 usage、log warn、hook exit 0。
- `extract_*` 對畸形輸入回空集合，不丟例外。
- ledger 以 append 寫入；單筆寫失敗不影響 hook 主流程（擷取/import 優先）。

## 6. 測試（TDD）

- **usage.py 單元**：`extract_offered` 從樣本 brief 抽正確 (id,title)；`extract_cited` 認 `[[sl-id]]` 與裸 `sl-id`、過濾非 offered；`extract_matched` 認標題出現、排除已 cited、忽略過短/空標題；**注入的 brief 文字本身不算 used**（給 assistant-only 文字才算）。
- **SessionEnd 整合**：給 offered 檔 + 假 transcript（含 assistant cite 與 user 文字）→ 正確寫出 memory_usage event；缺 offered/transcript → 不寫 event、不報錯。
- **CLI**：聚合樣本 ledger → per-slice 計數與彙總正確；`--since` 過濾。

## 7. 驗收

- [ ] 真實 claude session 後，`runtime/ledger/memory_usage.jsonl` 有對應 event（offered 數正確）。
- [ ] `psc memory usage` 能列出「過去 N 天哪些 slice 被 cited/matched 幾次」。
- [ ] brief 帶引用前言；offered 檔每 session 落地。
- [ ] hook 任一錯誤不影響既有擷取/注入（回歸測試）。

## 8. 部署順序

1. merge usage.py + hook 改動 + CLI（含測試）。
2. 部署（hooks 自 repo editable 載入，毋須重裝；新 session 即生效）。
3. 觀察數日，用 `memory usage` 看 cited/matched 是否累積。
4. 後續（另案）：把 usage 接回 brief relevance 排序與 janitor decay。
