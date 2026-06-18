## 1. TDD RED（先寫失敗測試）

- [ ] 1.1 新增 `tests/test_persona_phase4_fanout_autonomy.py`，`FrontmatterTests`：`parse_spec_frontmatter` 對 auto+depends_on / hold+拼錯+缺 key / 無 frontmatter 三類 fixture 的解析（`autonomy` 模組尚不存在 → RED）
- [ ] 1.2 同檔 `ScanTests`：`scan_specs` 暫存目錄回確定性排序 metas、含 path、目錄不存在回 `[]`（RED）
- [ ] 1.3 同檔 `CycleTests`：`detect_cycles` 對直接/間接環 raise、非環不 raise、指向不存在 id 不算環；`ready_units` 有環整批 raise（RED）
- [ ] 1.4 同檔 `ReadyTests`：預設 hold 不就緒、無 plan 不就緒、`depends_on` 未滿足/滿足以注入 fake `is_satisfied` 切換、`default_is_satisfied` 讀暫存 handoff `gate_status`（RED）
- [ ] 1.5 同檔 `FanoutTests`：`dispatch_ready` 以 **fake dispatcher** 驗精確派出就緒集（次數/`task`/`persona`、非就緒不派）；再以真 `Dispatcher` 配 fake seam + 暫存 registry 驗各記一筆 job（RED）
- [ ] 1.6 同檔 `CliTests`：`main(["ready", ...], is_satisfied=...)` 列就緒、`main(["fanout", ...], 全注入 fake)` 派就緒集、循環相依時 exit 非零（RED）
- [ ] 1.7 跑測試確認 RED 為「預期原因」（缺模組/缺屬性），捕捉輸出為證據

## 2. 實作 autonomy.py — frontmatter 解析（預設 HOLD）

- [ ] 2.1 新增 `paulshaclaw/coordinator/autonomy.py`：`parse_spec_frontmatter(path)` 以 `yaml.safe_load` 解析開頭 `---`...`---` 區塊；無合法 frontmatter → `dispatch='hold'`、`slice_id=None`、`plan=None`、`depends_on=[]`、含 `path`
- [ ] 2.2 `dispatch` 僅字面值 `auto` 取 `'auto'`，其餘一律 `'hold'`（硬約束）；`depends_on` 非 list/缺 → `[]`，單一字串容錯成單元素 list
- [ ] 2.3 RED → GREEN（`FrontmatterTests`）

## 3. 實作 scan_specs（確定性掃描）

- [ ] 3.1 `scan_specs(specs_dir)`：`sorted(Path(specs_dir).glob('*.md'))` 逐檔 `parse_spec_frontmatter`，回 metas；目錄不存在 → `[]`
- [ ] 3.2 RED → GREEN（`ScanTests`）

## 4. 實作 detect_cycles + ready_units（DAG + 三條件 + 可注入 is_satisfied）

- [ ] 4.1 `detect_cycles(metas)`：以 `slice_id` 為節點、`depends_on` 為邊，DFS 三色偵測回邊 → `raise ValueError`（帶 cycle path）；指向不存在 id 的邊不算環
- [ ] 4.2 `ready_units(metas, is_satisfied)`：**先 `detect_cycles`**；回 `dispatch=='auto'` ∧ `plan` 非空 ∧ `all(is_satisfied(dep) for dep in depends_on)`；確定性序；`is_satisfied` 為必注入參數（無預設值）
- [ ] 4.3 `default_is_satisfied(slice_id, handoff_dir='runtime/handoff')`：讀 `<dir>/<slice_id>.json`，`gate_status=='passed'` → True，否則/壞檔/不存在 → False（fail-closed）
- [ ] 4.4 RED → GREEN（`CycleTests` + `ReadyTests`）

## 5. 實作 dispatch_ready（fan-out，reuse Phase 2 Dispatcher）

- [ ] 5.1 `dispatch_ready(metas, is_satisfied, dispatcher, persona='builder')`：算 `ready_units`，對每個就緒單位 `dispatcher.dispatch(task=slice_id, persona=persona, pane_id=f"%{i}", command=f"# dispatch {slice_id} (plan={plan})")`，蒐集回的 job；不重寫 dispatch/registry、不派非就緒
- [ ] 5.2 RED → GREEN（`FanoutTests`，含 fake dispatcher 與真 `Dispatcher`+fake seam 兩路）

## 6. 擴充 cli.py（ready/fanout 子命令，main(argv) 加 is_satisfied 注入）

- [ ] 6.1 `_build_parser` 加 `ready --specs-dir` 與 `fanout --specs-dir [--persona]` 子命令（既有 `dispatch`/`jobs`/`stat` 不動）
- [ ] 6.2 `main(argv=None, *, registry=None, pane_sender=None, worktree_creator=None, is_satisfied=None) -> int`：`ready` → `scan_specs`+`ready_units`，印 JSON；`fanout` → 以注入或預設 seam 組 `Dispatcher`、`dispatch_ready`，印 dispatched jobs JSON；`is_satisfied` 未注入 → `default_is_satisfied`
- [ ] 6.3 `ready`/`fanout` 偵測循環相依（`ValueError`）→ stderr + exit 非零
- [ ] 6.4 RED → GREEN（`CliTests`）

## 7. 不回歸與 scope 紀律

- [ ] 7.1 確認 `core/daemon.py`、`core/config.py` 未被修改（`git diff --name-only` 不含這兩檔）
- [ ] 7.2 確認未重寫 `dispatcher.py` / `registry.py` / `seams.py`（reuse Phase 2；`dispatch_ready` 僅呼 `Dispatcher.dispatch`）
- [ ] 7.3 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（僅可接受既知 2 個 stage11 textual 環境失敗 `query_one`；`test_hooks.py`/`test_importer_cli.py`/`test_skillopt_loop.py` 全套件資源壓力下偶發 flake → 單獨重跑確認綠，非本 change 回歸）

## 8. 驗證

- [ ] 8.1 `openspec validate persona-phase4-fanout-autonomy --strict` 通過
- [ ] 8.2 `python -m unittest tests.test_persona_phase4_fanout_autonomy -v` 全綠
- [ ] 8.3 全套件不回歸（同 7.3）
