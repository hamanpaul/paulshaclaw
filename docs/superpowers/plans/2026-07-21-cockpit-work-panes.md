# Plan：cockpit WORK panes 可用性修正（issue #249）

目標 repo：paulshaclaw｜對應 issue：#249｜PR body 須 `Closes #249`

## 問題

cockpit WORK 面板 `tmux list-panes -a` 撈全 tmux server（13 session/~40 pane），`store.py` `candidate_section` 不收斂、summary 全撞 hostname `9900X`、看不出 cockpit 自身 pane。

## 範圍（僅動這些檔）

- `paulshaclaw/cockpit/tmux.py`
- `paulshaclaw/cockpit/store.py`
- `paulshaclaw/cockpit/models.py`
- `paulshaclaw/cockpit/app.py`（僅 WORK 面板副標的 you-are-here）
- `tests/test_stage11_operator_cockpit.py`（TDD）

## TDD 任務（紅→綠，逐項）

### 1. summary fallback（撞名 hostname）
- `models.py`：`PaneRecord` 新增 `pane_current_path: str = ""`、`host_short: str = ""`。
- `tmux.py`：`LIST_PANES_FORMAT` 追加 `#{pane_current_path}`、`#{host_short}`；`parse_list_panes` 解析（維持對 9/10/11 欄舊格式的容錯，新增欄採「有就取、無則空字串」）。
- `tmux.py`：`derive_summary(pane)` 邏輯改為：
  1. `title` 非空 **且** `title != host_short` → 用 `title`。
  2. 否則若 `command == "minicom"` → 既有 `_minicom_summary`。
  3. 否則若 `pane_current_path` 非空 → cwd basename（`Path(pane_current_path).name`），空 basename（`/`）退 `/`。
  4. 否則 → `[command]`。
- 測試：兩個 title 皆 `9900X`（== host_short）但 cwd 不同的 pane → summary 應不同（各自 cwd basename）。

### 2. 清單收斂到自身 session
- `store.py`：`candidate_section` 預設只收 `pane.session_name == self.cockpit_session_name` 的 pane（仍排除 cockpit pane 與 active-slot pane）。
- 排序鍵：自身 window（`cockpit_window_index`）的 pane 排在同 session 其他 window 之前；其餘沿用既有 `(window_index 數值, pane_id)`。
- 保留 `active-slot 收斂到自身 window` 既有行為不變。
- 測試：跨 3 個 session 的 panes 輸入 → `candidate_section` 只含 cockpit session 的、且自身 window 在前；他 session pane 不出現。

### 3. you-are-here 自我定位
- `app.py`：WORK 面板副標（`_set_border(work_list, "WORK · panes", subtitle)`）在既有 `N panes` / degraded 之外，補上 cockpit 自身 `session:window`（例：`main:0 · N panes`）。純顯示，fail-soft。
- 測試：副標含 cockpit 的 `cockpit_session_name` 與 window index。

## 驗收

- [ ] 同 window 多個 hostname-title 的 idle bash pane summary 可彼此區分
- [ ] `candidate_section` 預設不含他 session pane，自身 window 優先
- [ ] WORK 副標顯示 cockpit 自身 session:window
- [ ] `python -m pytest tests/test_stage11_operator_cockpit.py -q` 綠、全套無回歸

## 邊界

- 不改 tmux `list-panes -a`（跨 server 撈仍在資料層，收斂在 store 層做——保留未來「顯式切他 session」擴充空間）。
- 不動 JOBS 面板（屬 #248）。
