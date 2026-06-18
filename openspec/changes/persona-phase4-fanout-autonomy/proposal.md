## Why

設計 §9（manager fan-out + autonomy gate）要 manager 在 brainstorm 產出 task list 後，掃 `docs/superpowers/specs/*.md` 的 frontmatter，挑「就緒」的 task **各開一個 worktree+pane 並行** fan-out 跑整條 build pipeline，其餘維持 `hold` 等人類。Phase 2 已交付派工原語（`paulshaclaw/coordinator/` 的 `JobRegistry` / `Dispatcher` / seams / CLI），但「掃 frontmatter → 判就緒 → 派就緒集」這層 **autonomy gate / fan-out 排程器**尚不存在。

並且 issue [#104](https://github.com/hamanpaul/paulshaclaw/issues/104) 指出原 §9 隱含假設各 task 彼此獨立並行，實際平行開發有跨單位相依（如 persona Phase 1 依賴 Phase 0 merged）。缺乏顯式相依宣告，manager 可能在上游未完成前就派工，造成衝突或白工。#104 要 autonomy frontmatter 增列 `depends_on: [ids]`，fan-out 從「派所有 auto」升級為 **DAG 排程**：唯有 `dispatch: auto` 且有對應 plan 且 `depends_on` 全數滿足才釋放該單位；並 **偵測循環相依 → 報錯、不派工**。

本 change 交付設計 §9 + #104 的 **autonomy gate + depends_on DAG fan-out**，為一個**自我封裝、可完整單元測試**的新模組 `paulshaclaw/coordinator/autonomy.py` 與 CLI 擴充。所有派工**reuse Phase 2 `Dispatcher`**（不重寫 dispatch/registry 邏輯），副作用經注入 seam，測試一律注入 **fake dispatcher**（或真 `Dispatcher` 配 fake seam），**不啟動真 copilot / 真 tmux / 真 git**。預設 `hold`（沒宣告 = 不自主派工），相依「滿足」判定來源 **pluggable**（注入 `is_satisfied(slice_id) -> bool`，#104 留作實作定案），測試穩定。

## What Changes

- 新增 `paulshaclaw/coordinator/autonomy.py`：
  - `parse_spec_frontmatter(path) -> dict`：以 PyYAML 解析開頭 `---` frontmatter，回 `{dispatch ('auto'|'hold', 預設 'hold'), slice_id, plan (path 或 None), depends_on (list, 預設 [])}`；無 frontmatter / 無 `dispatch` key → 視為 `hold`（fail-safe 預設 HOLD）。
  - `scan_specs(specs_dir) -> list[meta]`：掃目錄下 `*.md`，逐檔 `parse_spec_frontmatter`，回各 meta（含 `path`），確定性排序。
  - `detect_cycles(metas)`：以 `slice_id` 為節點、`depends_on` 為邊建圖，偵測環 → `raise ValueError`（不派工）。
  - `ready_units(metas, is_satisfied) -> list[meta]`：**先呼叫 `detect_cycles`**；回 `dispatch=='auto'` 且 `plan` 非空 且每個 `depends_on` 經 `is_satisfied` 為真者；確定性排序。
  - `dispatch_ready(metas, is_satisfied, dispatcher, persona='builder')`：算 `ready_units`，對每個就緒單位經注入的 Phase 2 `Dispatcher` 派一筆 job（一單位一 job，pane+worktree 天然隔離故並行安全），回 dispatched jobs。
  - `default_is_satisfied`：提供一個預設判定（讀 `runtime/handoff/<slice_id>.json` 的 `gate_status == 'passed'`），但 `dispatch_ready` / `ready_units` 一律收注入 predicate（#104 把判定來源留開放：merged-to-main vs handoff gate_status）。
- 擴充 `paulshaclaw/coordinator/cli.py`：新增子命令 `ready`（列就緒單位）與 `fanout`（派就緒集）；`main(argv, *, registry=None, pane_sender=None, worktree_creator=None, is_satisfied=None) -> int` 仍可注入測試（fanout 用注入或預設 seam 接 `Dispatcher`）。
- 新增測試 `tests/test_persona_phase4_fanout_autonomy.py`：frontmatter parse（auto/hold/missing/含 depends_on）；預設 hold 不就緒；`depends_on` 未滿足 → 不就緒、滿足 → 就緒；環 → raise；`fanout` 經 **fake dispatcher** 精確派出就緒集。全程 fake，無真 copilot/tmux/git。
- **本階段不動** `core/daemon.py`、`core/config.py`（scope 紀律）；不重寫 `Dispatcher`/`JobRegistry`（reuse Phase 2）；不啟用 enforce 護欄（persona ①②③ 屬另線）。

## Capabilities

### Modified Capabilities

- `coordinator-cli`: 在既有 minimal 派工原語上新增 **autonomy gate + depends_on DAG fan-out** 層——frontmatter 解析（預設 HOLD）、spec 掃描、循環相依偵測（refuse）、就緒判定（`dispatch:auto` ∧ 有 plan ∧ `depends_on` 全滿足、可注入 `is_satisfied`）、reuse Phase 2 `Dispatcher` 的 fan-out（一單位一 job、並行安全），與 `ready` / `fanout` CLI 子命令（`main(argv)` 可注入測試）。

## Impact

- 代碼：新增 `paulshaclaw/coordinator/autonomy.py`；擴充 `paulshaclaw/coordinator/cli.py`（`ready` / `fanout` 子命令 + `is_satisfied` 注入點）；新增 `tests/test_persona_phase4_fanout_autonomy.py`。
- 設計依據：`docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md` §3 / §9 / §11（Phase 4）/ §12 / §13；issue [#104](https://github.com/hamanpaul/paulshaclaw/issues/104)（depends_on DAG）。
- 實作計畫：`docs/superpowers/plans/2026-06-18-persona-phase4-fanout-autonomy.md`。
- 無 runtime 行為變更（新模組無既有消費者，CLI 為 opt-in；預設 HOLD 故掃到無 `dispatch:auto` 的 spec 不會派工）、無新增外部依賴（PyYAML 既為前提，`tmux` / `git` 僅在 Phase 2 真 seam 內呼叫、測試以 fake 旁路）；`core/daemon.py` / `core/config.py` 維持不動。
