# Stage 11 Cockpit — Multi-Session Pane Listing Design

- Date: 2026-04-28
- Status: proposed
- Owner: @hamanpaul
- Topic: Stage 11 cockpit 改為列出本機所有 tmux session 的 pane，並支援跨 session swap

## 0. 背景

`scripts/start.sh` 帶起 cockpit 後，使用者發現列表只看得到 cockpit 所在 session 的 pane，而非本機所有 session 的 pane。這跟「operator cockpit 應該掌控整台機器的 tmux fleet」的預期不符。

根本原因：`paulshaclaw/cockpit/tmux.py` 的 `TmuxClient.list_panes` 呼叫 `tmux list-panes`（無 `-a`），只列當前 session。改 `-a` 之後還會牽動 active slot 的判斷，因為現有狀態機是用座標 `(left, top)` 當 anchor，而每個 session 各有獨立座標空間，多 session 後會重疊。

## 1. 目標與非目標

### 1.1 目標

- Cockpit 列出本機所有 tmux session/window/pane
- Swap (Enter) 動作可跨 session 自動運作（pane ID 全機唯一，`tmux swap-pane` 用 ID 即可跨 session）
- 提供 hotkey help：Footer 簡短即時提示 + `?` 鍵彈出完整說明 modal
- 不破壞既有的「active slot」「selected」「return to cockpit」狀態機語意

### 1.2 非目標

- 不新增跨 session goto/switch-client 動作
- 不分組顯示（不做每 session header），維持平面列表
- 不改 Stage 1 / Stage 9 / `LayoutActionService` / coordinator 整合
- 不改 `start.sh`

## 2. 關鍵決策

| 議題 | 決策 | 理由 |
|---|---|---|
| Pane 列舉 | `tmux list-panes -a` | 直接取全機 panes |
| Active 槽 | Cockpit-session-local：只取 cockpit 所在 session 的 active | 多 session 下座標重疊，必須加 session 過濾才不會誤判 |
| Swap | 既有 `LayoutActionService.swap_selected_with_active` 不動 | tmux pane ID 全機唯一，`swap-pane -s %X -d %Y` 自動跨 session |
| 顯示 | 平面列表，label = `session:window %ID title cmd` | 改動最小、5–30 個 pane 規模分組無收益 |
| 排序 | `(session_name, window_index, pane order)` | 直觀且可預期 |
| Goto | 不做 | YAGNI；Swap 已能滿足「把工作拉到面前」 |
| Help | Footer (永遠顯示) + `?` modal (詳細) | Footer 處理「忘了哪個鍵」、modal 處理「第一次看需要解釋」 |

## 3. 元件變更

### 3.1 `paulshaclaw/cockpit/models.py`

`PaneRecord` 新增兩個欄位：

```python
@dataclass(frozen=True)
class PaneRecord:
    pane_id: str
    session_name: str       # 新增
    window_index: str       # 新增（保 str 容許 base-index 非零）
    title: str
    command: str
    left: int
    top: int
    width: int
    height: int
    active: bool
    preview: tuple[str, ...]
```

### 3.2 `paulshaclaw/cockpit/tmux.py`

- `LIST_PANES_FORMAT` 前面加 `#{session_name}\t#{window_index}\t`
- `list_panes` 呼叫改為 `tmux list-panes -a -F <format>`，移除 `_target()`
- `parse_list_panes` 處理多 2 欄；長度檢查改成 9 / 10
- `TmuxClient.__init__` 移除 `session_name` 參數

### 3.3 `paulshaclaw/cockpit/store.py`

- `CockpitState` 新增欄位 `cockpit_session_name: str`
- `from_panes` 簽名加 `cockpit_session_name`
- `choose_startup_slot` 簽名加 `cockpit_session_name`，candidate 過濾條件改為 `pane_id != cockpit_pane_id AND session_name == cockpit_session_name`
- `active_section` 過濾條件加 `session_name == cockpit_session_name`
- `candidate_section` = 其餘所有 pane（含其他 session 全部 + 本 session 非 active）
- `candidate_section` 結果以 `(session_name, window_index, pane_id)` 排序
- `refresh` 的 `active_exists` 也加 session 過濾

### 3.4 `paulshaclaw/cockpit/app.py`

- BINDINGS 補完 description（`"↑/↓ 選擇"`、`"Enter 把選中的 pane 換到我面前"`、`"c 回 cockpit"`、`"? 顯示說明"`）— 僅補既有與本次新增 binding，不額外加 quit 鍵（避免擴張 scope）
- 新增 `Binding("question_mark", "show_help", "Help")`
- 新增 `action_show_help`：`self.push_screen(HelpModal())`
- `_refresh_widgets` 的 pane label 改為 `f"{prefix} {pane.session_name}:{pane.window_index} {pane.pane_id} {pane.title}"`
- `active-slot` Static 顯示加上 session/window 前綴

### 3.5 `paulshaclaw/cockpit/help.py`（新檔）

- `HelpModal(ModalScreen)`：靜態文字面板，從 `CockpitApp.BINDINGS` 動態生成 hotkey 表 + 多 session 行為說明
- 按 esc 關閉（不接其他鍵，避免與 cockpit 主畫面 binding 衝突）

### 3.6 `paulshaclaw/cockpit/__main__.py`

- 從 `panes` 中找出 `pane_id == args.cockpit_pane` 的 record，取其 `session_name` 推導 `cockpit_session_name`，傳入 `from_snapshot`
- 既有「找不到 cockpit pane → 回 1」錯誤處理保留

## 4. 資料流

```
tmux list-panes -a
  → TmuxClient.list_panes()
    → parse_list_panes()  (含 session_name, window_index)
      → CockpitState.from_panes(cockpit_pane_id, cockpit_session_name)
        → choose_startup_slot()  (限定 cockpit_session_name)
        → active_section / candidate_section  (session-scoped 過濾 + 排序)
          → CockpitApp._refresh_widgets()  (label 含 session:window 前綴)
```

Swap 動作沿用既有：`actions.swap_selected_with_active(selected_pane_id, active_pane_id)` 內部跑 `tmux swap-pane -s %X -d %Y`，pane ID 全機唯一所以跨 session 自動 work。

## 5. 錯誤處理

- **Cockpit pane 找不到**：既有錯誤處理保留（`__main__.py` 印 stderr 並回 1）
- **其他 session 的 pane 消失**：不視為 degraded，`refresh` 的 `active_exists` 已只看 cockpit-session
- **Cockpit 所在 session 被 kill**：cockpit pane 本身會死、TUI 退出，無需特別處理
- **`tmux list-panes -a` 失敗**：既有 try/except 路徑保留，回 `()`

## 6. 測試

### 6.1 既有測試更新（簽名/欄位調整，不改用例語意）

- `test_parse_list_panes_extracts_geometry` — raw 字串改為 9 欄，加上 session/window 驗證
- `test_parse_list_panes_skips_malformed_numeric_fields` — raw 字串補欄位
- `test_choose_startup_slot_excludes_cockpit_even_when_same_size` — `PaneRecord` 構造補欄位、`choose_startup_slot` 加 `cockpit_session_name` 引數
- `test_state_segments_active_and_candidate_sections` — 同上
- `test_state_marks_active_slot_lost_when_no_pane_matches_anchor` — 同上
- `Stage11AppTests` 兩個用例 — `PaneRecord` 構造補欄位
- `test_main_exits_with_error_when_cockpit_pane_is_missing` — 不變

### 6.2 新增測試

1. `test_list_panes_uses_dash_a_flag` — patch `subprocess.run` 驗證 cmd 含 `-a` 且 format 含 `#{session_name}` `#{window_index}`
2. `test_parse_list_panes_extracts_session_window` — raw 含兩 session pane，驗證解析
3. `test_choose_startup_slot_only_considers_cockpit_session` — session 1 有最大 pane 也不能被選
4. `test_active_section_excludes_other_sessions_with_same_anchor` — 重疊座標但跨 session，只 cockpit-session 那個算 active
5. `test_candidate_section_sorted_by_session_window_pane` — 多 session 多 window 排序驗證
6. `test_refresh_active_lost_only_when_cockpit_session_pane_gone` — 其他 session 的 pane 消失不觸發 `active-slot-lost`
7. `test_main_derives_cockpit_session_from_pane_record` — mock list_panes 回帶 session_name 的 cockpit pane，驗證下游收到正確 session
8. `test_question_mark_opens_help_modal` — pilot.press("?")，驗證 `app.screen` 是 `HelpModal`
9. `test_help_modal_dismisses_on_escape` — esc 關閉
10. `test_help_modal_lists_all_bindings` — modal 文字含每個 BINDINGS description

### 6.3 整合測試新增

11. `test_e2e_multi_session_pane_visible_in_candidate_list` — fake TmuxClient 回兩 session pane，跑 `--once` smoke check

### 6.4 驗證命令

```
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py tests/test_stage11_operator_cockpit_e2e.py -v
```

## 7. 不變項

- `LayoutActionService` 三個方法（swap/focus/return）介面與實作不動
- `ArtifactAdapter` 與 coordinator jobs 整合不動
- `start.sh` 不動
- Stage 1 / Stage 9 / Stage 11 之外的模組不動
