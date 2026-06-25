## Context

完整設計見 `docs/superpowers/specs/2026-06-25-memory-usage-telemetry-design.md`。記憶採用評估（#139 P2）發現「注入後 agent 是否真用」是黑盒；本 change 做 #148 A 案第一刀。adversarial review（#148）已折回：ledger 必須存 offered id 陣列使其 self-sufficient。

## Goals / Non-Goals

**Goals:**
- 每 session 記 offered（三家）；claude session 記 used（cited + matched）。
- durable usage ledger（含 offered id 陣列）+ 查詢 CLI 回答「過去 N 天哪些 slice 被用幾次」。

**Non-Goals:**
- 接回 brief relevance 排序、janitor decay（後續，需先有數據）。
- codex/copilot 的 used 解析（先只 offered）。
- 強制 agent 引用（只提示）。

## Decisions

- **used = hybrid**：cited（顯式 `[[sl-id]]`，強訊號）+ matched（標題 ≥8 字 text-match，弱訊號）分開記。
- **claude-only 先行**：used 只做 claude（transcript_path JSONL）；offered 三家共用。
- **引用前言放 brief**：隨記憶注入、三家共用。
- **ledger self-sufficient**：event 存 offered id 陣列（非數量），CLI 僅讀 ledger，不 join 易失 wakeup 檔（adversarial review [high]）。
- **best-effort**：所有 hook 路徑沿 #141 韌性，任何錯誤只 log、exit 0，既有擷取/注入不受影響。
- usage.py 為純函式單一真相源，hook 與 CLI 共用。

## Risks / Trade-offs

- **引用合規率**：agent 未必照引用前言標註 → cited 偏低；matched 作 backstop 補涵蓋率，兩訊號分開記可分辨可信度。
- **matched 假陽性**：標題巧合出現 → 限 ≥8 字標題、且只比 assistant 文字（排除注入 brief）降低誤判。
- **wakeup 檔競態**：同 session 多次 SessionStart（clear/compact）會覆寫 offered 檔；以最後一次 brief 為準，可接受。
