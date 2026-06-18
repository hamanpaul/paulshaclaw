## ADDED Requirements

### Requirement: Autonomy frontmatter 解析預設 HOLD 且支援 depends_on

`coordinator-cli` SHALL 提供 `paulshaclaw/coordinator/autonomy.py`，其 `parse_spec_frontmatter(path) -> dict` MUST 以 PyYAML（`safe_load`）解析 superpowers spec 開頭的 `---` frontmatter 區塊，回傳含 `dispatch`、`slice_id`、`plan`、`depends_on`、`path` 鍵的 dict。`dispatch` MUST 僅在 frontmatter 明確為字面值 `auto` 時為 `'auto'`，其餘所有情況（缺 `dispatch` key、值非 `auto`、無合法 frontmatter、檔案不以 `---` 起頭）MUST 預設為 `'hold'`（硬安全要求：未明確宣告即不自主派工）。`slice_id` 與 `plan` 缺省 MUST 為 `None`；`depends_on` 缺省或非 list MUST 為 `[]`（單一字串值 MAY 容錯為單元素 list）。`parse_spec_frontmatter` MUST 容忍完全無 frontmatter 的檔案而不 raise（視為 hold）。

#### Scenario: dispatch:auto 帶 slice_id/plan/depends_on 被正確解析

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests.test_parse_auto_with_depends_on -v`
- **THEN** 測試 MUST 驗證一份 frontmatter 含 `dispatch: auto`、`slice_id`、`plan`、`depends_on: [a, b]` 的 spec 被解析為 `dispatch=='auto'`、對應的 `slice_id`/`plan`、`depends_on==['a','b']`

#### Scenario: 缺 dispatch 或值非 auto 預設 hold

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests.test_parse_hold_and_default -v`
- **THEN** 測試 MUST 驗證 `dispatch: hold`、拼錯的 dispatch 值、以及無 `dispatch` key 三種 frontmatter 皆解析為 `dispatch=='hold'`，且 `depends_on` 缺省為 `[]`

#### Scenario: 無 frontmatter 的 spec 視為 hold 不 raise

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests.test_parse_missing_frontmatter_is_hold -v`
- **THEN** 測試 MUST 驗證一份不以 `---` 起頭（無 frontmatter）的 markdown 被解析為 `dispatch=='hold'`、`slice_id is None`、`depends_on==[]`，且 `parse_spec_frontmatter` MUST NOT raise

### Requirement: scan_specs 確定性掃描 spec 目錄

`coordinator-cli` 的 `autonomy.scan_specs(specs_dir) -> list[dict]` MUST 掃描 `specs_dir` 下的 `*.md`，對每檔呼叫 `parse_spec_frontmatter`，回傳各 meta 的清單（每筆含 `path`）。輸出順序 MUST 確定性（依路徑排序）。`specs_dir` 不存在時 MUST 回傳空清單，MUST NOT raise。

#### Scenario: 掃描目錄回確定性排序的 metas

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ScanTests.test_scan_specs_deterministic -v`
- **THEN** 測試 MUST 以暫存目錄放數份 spec，驗證 `scan_specs` 回的 meta 數量與檔案數一致、含各自 `path`、且順序為路徑排序（確定性）

### Requirement: depends_on 循環相依偵測並 refuse

`coordinator-cli` 的 `autonomy.detect_cycles(metas)` MUST 以各 meta 的 `slice_id` 為節點、`depends_on` 為有向邊建圖，當存在循環相依時 MUST raise `ValueError`（refuse，不派工）。指向不存在於 metas 的 `slice_id` 的 `depends_on` MUST NOT 被視為循環（交由 `is_satisfied` 判定其滿足與否）。`ready_units` MUST 在計算就緒集前先呼叫 `detect_cycles`，使有環時整批拒絕、不釋放任何單位。建圖時若偵測到**重複的 `slice_id`**（兩筆以上 meta 共用同一 `slice_id`，身分不明確），MUST 在 DFS 前 raise `ValueError`（refuse）：靜默以後者覆寫前者的 `depends_on` 邊會遮蔽真環，且下游 fan-out 會對同一 `feature/<slice_id>` 重複派工（違反「一單位一 job」）。

#### Scenario: 直接與間接循環相依 raise

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CycleTests.test_detect_cycle_raises -v`
- **THEN** 測試 MUST 驗證直接環（A→B→A）與間接環（A→B→C→A）的 metas 使 `detect_cycles` raise `ValueError`，且非環圖（A→B、C→B）MUST NOT raise

#### Scenario: 重複 slice_id 直接 refuse 且不遮蔽真環

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CycleTests.test_duplicate_slice_id_refused tests.test_persona_phase4_fanout_autonomy.CycleTests.test_duplicate_slice_id_does_not_mask_cycle -v`
- **THEN** 測試 MUST 驗證兩筆共用同一 `slice_id` 的 metas 使 `detect_cycles`／`ready_units` raise `ValueError`（訊息含「重複 slice_id」），且 `[A→B, A→[], B→A]`（第二個 A 試圖覆寫 A→B）仍 MUST raise（不得因覆寫而漏掉 A↔B 真環）

#### Scenario: ready_units 在有環時整批拒絕

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CycleTests.test_ready_units_refuses_on_cycle -v`
- **THEN** 測試 MUST 驗證對含循環相依的 metas 呼叫 `ready_units(metas, is_satisfied)` 會 raise `ValueError`（先 `detect_cycles`），MUST NOT 回傳部分就緒集

### Requirement: ready_units 三條件就緒判定且 is_satisfied 可注入

`coordinator-cli` 的 `autonomy.ready_units(metas, is_satisfied)` MUST 回傳同時滿足下列條件的 metas：`slice_id` 為非空字串（有身分）、`dispatch == 'auto'`、`plan` 為非空字串、且每個 `depends_on` 經注入的 `is_satisfied(slice_id) -> bool` 皆為真（`depends_on` 為空時自然滿足）。`slice_id` 為 `None`／非字串／空字串的單位無身分（無法成為 `depends_on` 目標、無法被追蹤或交接），依 fail-safe 立場 MUST NOT 就緒。`is_satisfied` MUST 為可注入參數（呼叫者決定相依「滿足」的判定來源，例 merged-to-main 或 handoff `gate_status`）。`coordinator-cli` SHALL 另提供預設 `default_is_satisfied(slice_id, handoff_dir='runtime/handoff') -> bool`（讀 `<handoff_dir>/<slice_id>.json` 且 `gate_status == 'passed'` → True，否則 False；檔不存在/壞檔 → False，fail-closed），但 `ready_units`/`dispatch_ready` MUST 不寫死此來源、一律收注入 predicate。輸出順序 MUST 確定性。

#### Scenario: 預設 hold 的單位不就緒

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_hold_not_ready -v`
- **THEN** 測試 MUST 驗證一個 `dispatch=='hold'`（或無 plan）的 meta 不出現在 `ready_units` 結果中，即使其 `depends_on` 全滿足

#### Scenario: depends_on 未滿足不就緒、滿足才就緒

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_depends_on_gates_readiness -v`
- **THEN** 測試 MUST 以注入的 fake `is_satisfied` 驗證：當某 `depends_on` 回 False 時該 auto+plan 單位不就緒；當 `is_satisfied` 對所有相依回 True 時該單位就緒；`depends_on` 為空的 auto+plan 單位恆就緒

#### Scenario: 無 slice_id 的單位不就緒

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_no_slice_id_not_ready -v`
- **THEN** 測試 MUST 驗證 `dispatch=='auto'` 且有 `plan` 但 `slice_id` 為 `None`／空字串的 meta 不出現在 `ready_units` 結果中（無身分 → fail-safe 不就緒）

#### Scenario: default_is_satisfied 讀 handoff gate_status

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.ReadyTests.test_default_is_satisfied_reads_gate_status -v`
- **THEN** 測試 MUST 以暫存 handoff 目錄驗證 `default_is_satisfied` 對 `gate_status=='passed'` 的 manifest 回 True、對非 passed 或不存在的 manifest 回 False

### Requirement: fan-out reuse Phase 2 Dispatcher 派出就緒集

`coordinator-cli` 的 `autonomy.dispatch_ready(metas, is_satisfied, dispatcher, persona='builder', git_runner=None) -> list` MUST 先以 `ready_units(metas, is_satisfied)` 算出就緒集，再對每個就緒單位經注入的 `dispatcher`（Phase 2 `Dispatcher`）呼叫 `dispatch(...)` 各派一筆 job（一單位一 job；隔離靠 per-worktree／pane，故並行安全），並回傳 dispatched jobs 清單。`dispatch_ready` MUST NOT 重新實作 dispatch/registry 邏輯（reuse Phase 2 `Dispatcher`），MUST NOT 對非就緒單位派工。`persona` MUST 預設為 `'builder'` 且可覆寫。`git_runner` MUST 為可選注入物：給定時 MUST 透傳給 `Dispatcher.dispatch(..., git_runner=...)`（沿用 Phase 2 既有 seam），使測試能以 fake `git_runner` 取代真 git；未給定時不傳（沿用 dispatcher 自身預設，並相容不收 `git_runner` 的 fake dispatcher）。因 `ready_units` 先 `detect_cycles`，`dispatch_ready` 對含循環相依或重複 `slice_id` 的 metas MUST raise `ValueError`（一筆都不派），且對無 `slice_id` 的單位 MUST NOT 以 `task=None` 派工。

#### Scenario: fanout 僅對就緒集經注入 dispatcher 各派一筆

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_dispatches_exactly_ready_set -v`
- **THEN** 測試 MUST 以 **fake dispatcher**（記錄 `dispatch` 呼叫）+ 一組含就緒與非就緒（hold／無 plan／depends_on 未滿足）的 metas 驗證：`dispatch` 被呼叫的次數等於就緒單位數、每次 `task` 對應就緒單位的 `slice_id`、`persona` 為注入值，且非就緒單位 MUST NOT 被派工

#### Scenario: fanout 經真 Dispatcher 配 fake seam（含 fake git_runner）不碰真副作用

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_with_real_dispatcher_fake_seams -v`
- **THEN** 測試 MUST 以真 `Dispatcher` 配 fake `PaneSender`／fake `WorktreeCreator`＋**注入 fake `git_runner`**＋暫存 `JobRegistry` 驗證就緒集被各記成一筆 job，且全程不啟動真 tmux／git／copilot（測試 MUST 以 spy 斷言真 `git` 子行程零呼叫、fake `git_runner` 各單位被呼叫一次）

#### Scenario: fanout 對無 slice_id 單位不以 task=None 派工

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_no_slice_id_not_dispatched -v`
- **THEN** 測試 MUST 驗證 `dispatch=='auto'`、有 `plan` 但 `slice_id` 為 `None` 的 meta 不被派工（`dispatch_ready` 回空清單、fake dispatcher 零呼叫），不得產生 `task=None`／`feature/None` 的 job

#### Scenario: fanout 對重複 slice_id refuse 不重複派工

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FanoutTests.test_dispatch_ready_refuses_duplicate_slice_id -v`
- **THEN** 測試 MUST 驗證兩份 metas 共用同一 `slice_id` 時 `dispatch_ready` raise `ValueError`（一筆都不派），不得對同一 `feature/<slice_id>` 重複派工

### Requirement: CLI 提供 ready/fanout 子命令且 main(argv) 可注入

`coordinator-cli` 的 `python -m paulshaclaw.coordinator` 入口 SHALL 新增子命令 `ready --specs-dir <dir>`（輸出就緒單位的 JSON 清單）與 `fanout --specs-dir <dir> [--persona R]`（算就緒集、經 Phase 2 `Dispatcher` 派工、輸出 dispatched jobs 的 JSON）。`main(argv, *, registry=None, pane_sender=None, worktree_creator=None, is_satisfied=None, git_runner=None) -> int` MUST 在 Phase 2 簽名上新增可注入的 `is_satisfied`（未注入時用 `default_is_satisfied`）與可注入的 `git_runner`（`fanout` 透傳給 `dispatch_ready`／`Dispatcher.dispatch`；未注入時沿用 `Dispatcher` 預設真 git——測試一律注入 fake `git_runner` 以保證不啟動真 git），並 MUST 在未注入 seam 時接線真實 seam（不啟動真 tmux／worktree 由測試以注入 fake 保證）。偵測到循環相依時 `ready`／`fanout` MUST 將錯誤輸出至 stderr 並 exit 非零（refuse）。既有 `dispatch`／`jobs`／`stat` 子命令 MUST 維持不變。

#### Scenario: ready 子命令以注入 is_satisfied 列就緒單位

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests.test_main_ready_lists_ready_units -v`
- **THEN** 測試 MUST 以暫存 specs 目錄＋注入 `is_satisfied` 驗證 `main(["ready", "--specs-dir", d], is_satisfied=...)` 回 0 並輸出僅含就緒單位的 JSON

#### Scenario: fanout 子命令以注入 fake 派出就緒集

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests.test_main_fanout_with_fakes -v`
- **THEN** 測試 MUST 以注入的 fake seam＋暫存 registry＋注入 `is_satisfied`＋注入 fake `git_runner` 驗證 `main(["fanout", "--specs-dir", d], ...)` 回 0、就緒集各被記成一筆 job、輸出 dispatched jobs JSON，且全程不碰真 tmux／git／copilot（測試 MUST 以 spy 斷言真 `git` 子行程零呼叫）

#### Scenario: 循環相依時 ready/fanout exit 非零

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests.test_main_refuses_on_cycle -v`
- **THEN** 測試 MUST 以含循環相依的暫存 specs 目錄驗證 `main(["ready", "--specs-dir", d], ...)` 回非零並於 stderr 含循環相依訊息，MUST NOT 派工
