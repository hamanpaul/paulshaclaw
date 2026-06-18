## Context

設計 §9 列 manager fan-out + autonomy gate：brainstorm 產 task list 後，manager 掃 `docs/superpowers/specs/*.md` 的 frontmatter（`dispatch: auto | hold`，預設 `hold`；`slice_id`；`plan`），挑 `dispatch: auto` 且有對應 plan 的 task **各開 worktree+pane 並行** fan-out。其餘維持 `hold` 等人類在 brainstorm 補。

issue #104 在此之上加 `depends_on: [ids]`：fan-out 升級為 **DAG 排程**——單位 ready 條件為 `dispatch: auto` ∧ 有對應 plan ∧ `depends_on` 全部已「滿足」；同層無相依者並行、有相依者待上游完成才釋放；**循環相依 → 報錯、不派工**。#104 明言相依「滿足」的判定來源（merged-to-main vs handoff manifest `gate_status`）於實作時定案，故本設計把它做成 **pluggable predicate**。

Phase 2（`2026-06-18-persona-phase2-coordinator-cli`）已交付派工原語 `paulshaclaw/coordinator/`：`JobRegistry`（確定性 job_id、JSON 持久化、corrupt fail-closed）、`Dispatcher(registry, pane_sender, worktree_creator)`（`dispatch(task, persona, pane_id, command)` 建 worktree→送命令→記 job，並行安全）、seams（`PaneSender` / `WorktreeCreator` Protocol + tmux/git 真實作）、`cli.main(argv, *, registry, pane_sender, worktree_creator)`。本 change **reuse 這些零件**，只在其上加 autonomy gate / DAG / fan-out，**不重寫 dispatch/registry 邏輯**。

設計鐵律延續 Phase 2：所有副作用藏在可注入 seam 後，**單元測試一律注入 fake**（fake dispatcher，或真 `Dispatcher` 配 fake seam）——不啟動真 copilot、真 tmux、真 git worktree。

## Goals / Non-Goals

**Goals:**
- `parse_spec_frontmatter(path)`：PyYAML 解析開頭 `---` block，回 `{dispatch, slice_id, plan, depends_on}`；**容忍無 frontmatter（視為 hold）**、預設 `dispatch='hold'`、`depends_on=[]`、`plan=None`。
- `scan_specs(specs_dir)`：掃 `*.md`，回各 meta（含 `path`），**確定性排序**。
- `detect_cycles(metas)`：`depends_on` 成環 → **raise `ValueError`**（keyed by `slice_id`）。
- `ready_units(metas, is_satisfied)`：**先 `detect_cycles`**，回 `dispatch=='auto'` ∧ `plan` 非空 ∧ 每個 `depends_on` `is_satisfied` 為真者；確定性排序。
- `dispatch_ready(metas, is_satisfied, dispatcher, persona='builder')`：算 `ready_units`，每單位經注入 **Phase 2 `Dispatcher`** 派一筆 job，回 dispatched jobs。
- `default_is_satisfied`：一個預設判定（讀 `runtime/handoff/<slice_id>.json` 的 `gate_status == 'passed'`），但保持 predicate **可注入**。
- CLI `ready` / `fanout` 子命令；`main(argv)` 可注入 `is_satisfied` + seam 測試。
- 測試全 fake、確定性、不碰真副作用；全套件不回歸。

**Non-Goals:**
- 不改 `core/daemon.py` / `core/config.py`（scope 紀律）。
- 不重寫 `Dispatcher` / `JobRegistry` / seams（reuse Phase 2；fan-out 只 orchestrate）。
- 不做 enforce 護欄 / persona ①②③ contract render（Phase 1 / Phase 3 各自線）。
- 不啟動真 copilot；不組裝 copilot 指令字串以外的監督（dispatch 送的 command 由呼叫者/上層給；本 change fan-out 對每單位組一個含 `slice_id` 的最小 command 佔位，實際 prompt 拼裝屬 §5 ①，非本 change）。
- 不定案相依「滿足」終局來源（#104 留開放）；提供 `default_is_satisfied`（handoff gate_status）作預設，但一律可注入覆寫。

## Decisions

- **D1 — frontmatter 解析預設 HOLD（fail-safe）**：`parse_spec_frontmatter(path)` 讀檔，若內容**不以 `---` 起頭**或找不到第二個 `---`（無合法 frontmatter）→ 回 `{path, dispatch:'hold', slice_id:None, plan:None, depends_on:[]}`。有 frontmatter 則 `yaml.safe_load` 中間段：`dispatch` 僅當字面值為 `'auto'` 才取 `'auto'`，其餘（含缺 key / 非字串 / 拼錯）一律 `'hold'`——**硬約束「沒宣告 = HOLD」**。`slice_id` 取字串或 None；`plan` 取字串或 None；`depends_on` 取 list（單一字串容錯成單元素 list；非 list/缺 → `[]`）。`yaml.safe_load`（非 `load`）避免任意物件構造。
- **D2 — scan_specs 確定性排序**：`scan_specs(specs_dir)` 以 `sorted(Path(specs_dir).glob('*.md'))`（路徑字串序）迭代，逐檔 `parse_spec_frontmatter`，回 list。`specs_dir` 不存在 → 回 `[]`（非錯誤，呼應「掃不到就沒得派」）。排序確定性使 `ready_units` / fan-out 輸出可硬斷言。
- **D3 — depends_on DAG + 循環偵測（refuse）**：`detect_cycles(metas)` 以有 `slice_id` 的 meta 為節點建鄰接表（`slice_id -> depends_on`），DFS 三色（white/gray/black）偵測回邊；發現 gray→gray 邊即 `raise ValueError(f"depends_on 偵測到循環相依: {cycle_path}")`。指向不存在 `slice_id` 的 `depends_on`（外部/未掃到的相依）**不視為環**（留給 `is_satisfied` 判定其是否滿足）；只有形成回路才 refuse。`ready_units` **MUST 先呼叫 `detect_cycles`**，故有環時整批拒絕、不派任何工（fail-closed）。
- **D4 — ready 三條件 + pluggable is_satisfied**：`ready_units(metas, is_satisfied)`：先 `detect_cycles(metas)`；一單位 ready ⟺ (`meta['dispatch'] == 'auto'`) ∧ (`meta['plan']` 為非空字串) ∧ (`all(is_satisfied(dep) for dep in meta['depends_on'])`)。`is_satisfied: Callable[[str], bool]` **必為注入**（無預設參數值——強制呼叫者決定判定來源，符合 #104「來源實作定案」）。`depends_on` 為空時 `all([])==True` 自然滿足。回就緒 metas，順序沿用 `scan_specs` 的確定性序。
- **D5 — fan-out reuse Phase 2 Dispatcher（不重寫派工）**：`dispatch_ready(metas, is_satisfied, dispatcher, persona='builder') -> list[job]`：`ready = ready_units(metas, is_satisfied)`；對每個 `meta` 呼 `dispatcher.dispatch(task=meta['slice_id'], persona=persona, pane_id=<per-unit>, command=<per-unit>)`，蒐集回的 job。`dispatcher` 為注入物（型別上是 Phase 2 `Dispatcher`，測試可塞 fake，duck-typed 只需有 `dispatch(...)`）。**並行安全**靠 Phase 2 既有性質（每 job 自己的 worktree+pane，registry 多筆互不污染）；本 change 不自起執行緒——「並行」指各單位獨立 job/worktree/pane，可同時存活，不是 Python 並發。
  - **pane / command 的決定**：fan-out 對第 i 個就緒單位給 `pane_id = f"%{i}"`（佔位，真實 pane 分配屬上層 orchestrator/未來 wiring；測試以 fake 斷言每單位各自一個 pane），`command = f"# dispatch {slice_id} (plan={plan})"`（最小佔位；真實 copilot prompt 拼裝屬 §5 ① contract render，非本 change scope）。介面上 `dispatch_ready` 不負責拼 copilot 指令，只負責「把就緒集各派一筆」。
- **D6 — default_is_satisfied（預設來源 = handoff gate_status，可被覆寫）**：提供 `default_is_satisfied(slice_id, handoff_dir='runtime/handoff') -> bool`：讀 `<handoff_dir>/<slice_id>.json`，存在且 `gate_status == 'passed'` → True，否則 False（檔不存在/壞檔/非 passed → False，fail-closed：未證明滿足即不釋放下游）。這只是**預設 impl**；`ready_units` / `dispatch_ready` 一律收注入 predicate，故測試與未來「merged-to-main」來源可換入同介面（`Callable[[str], bool]`）。CLI `ready` / `fanout` 未注入時用 `functools.partial(default_is_satisfied)`。
- **D7 — CLI 邏輯/殼分離、可注入**：`cli.main(argv=None, *, registry=None, pane_sender=None, worktree_creator=None, is_satisfied=None) -> int` 在 Phase 2 簽名上加 `is_satisfied`。新增子命令：`ready --specs-dir <dir>`（印就緒單位的 `slice_id`/`plan` JSON 清單）、`fanout --specs-dir <dir> [--persona builder]`（算就緒集、經 `Dispatcher` 派工、印 dispatched jobs JSON）。`fanout` 內以注入或預設 seam（`JobRegistry()` / `TmuxPaneSender()` / `ScriptWorktreeCreator()`）組 Phase 2 `Dispatcher`；`is_satisfied` 未注入 → `default_is_satisfied`。偵測到循環相依 → 印錯誤到 stderr、exit 非零（refuse）。測試一律全注入 fake（fake dispatcher 經 monkeypatch 或注入 seam），不碰真 tmux/git/copilot。
- **D8 — 不重複定義 frontmatter schema 於別處**：`depends_on` / `dispatch` / `plan` / `slice_id` 的解析語意只在 `autonomy.parse_spec_frontmatter` 一處實作；CLI 與 fan-out 都消費其輸出 meta dict，不另解析 YAML。

## Risks / Trade-offs

- [預設 HOLD 可能「該派的沒派」] → 正是意圖（設計硬約束：沒明確 `dispatch: auto` 一律不自主派工，人類在 brainstorm 補）。誤殺方向安全（不會誤派），符合 fail-safe。
- [循環相依 refuse 會擋住整批 fan-out] → 正是 #104 要的（成環即無正確排程，寧可報錯也不亂派造成衝突/白工）；錯誤訊息帶 cycle path 供人修 frontmatter。
- [`depends_on` 指向不存在 slice_id 不算環、但可能永遠不滿足] → 交由 `is_satisfied` 判定（預設 handoff gate_status 找不到檔即 False，下游永不釋放，安全）；不在 `detect_cycles` 把它當錯誤，避免「外部相依/尚未掃到」被誤判成環。Trade-off：拼錯的 dep id 會靜默永不就緒而非報錯——可由 `ready` 子命令人工觀察就緒與否診斷。
- [`is_satisfied` 來源未定案（merged vs gate_status）] → #104 明言留開放；本設計用 pluggable predicate 吸收，`default_is_satisfied` 採 handoff `gate_status=='passed'`（與 Phase 1/3 manifest 一致），未來換 merged-to-main 只需換注入物，不動 DAG/fan-out。
- [fan-out 的 pane/command 為佔位] → 真實 pane 分配與 copilot prompt 拼裝屬 §5 ① / 未來 wiring，非本 change；本 change 聚焦「判就緒 → reuse Dispatcher 各派一筆」，介面留 `persona` 參數與 per-unit job，日後拼真指令不需改 DAG/ready 結構。
- [reuse Phase 2 Dispatcher 而非新寫] → 符合「不重複 dispatch/registry 邏輯」硬約束；風險為對 Phase 2 介面耦合（`dispatch(task, persona, pane_id, command)`），但該介面已穩定（archived spec）、且 fan-out 只 duck-type 呼 `dispatch`，測試可注入 fake 解耦。
