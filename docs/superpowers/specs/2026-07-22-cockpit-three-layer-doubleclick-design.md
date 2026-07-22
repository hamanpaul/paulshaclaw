---
dispatch: hold
slice_id: cockpit-three-layer
plan: null
depends_on: []
---

# Cockpit 三層直排 + 雙擊 swap + 自動歸位 設計

> 日期：2026-07-22 ｜ 狀態：v8.1（v8 定稿＝codex 對抗審查 8 輪 PASS；v8.1＝plan 審查揭露 #249 spec 漂移後之 §6 需求對照 truth-up，req 5 改 MODIFIED）｜ 分支：`feature/cockpit-three-layer`
> 範疇：stage11-operator-cockpit spec 修訂。前置脈絡：#248/#249（JOBS 接線、WORK 收斂）、#252（cost footer）皆已 merged。

## 1. 背景與決策脈絡

cockpit 現行版面是左右欄：左 WORK 清單、右 DETAIL（選中 pane 的 metadata + `capture-pane` preview + job 狀態）+ JOBS。本設計評估過兩條演進路線：

- **A 案（否決）**：DETAIL 加 send-keys 輸入列，把 cockpit 變跨 pane 控制台。否決理由：輸入列本質是盲打電傳（無補全、無 TUI 互動、回饋只有 20 行 preview），操作手感不可能贏「swap 過去原生操作」。
- **B 案（採用）**：拿掉 DETAIL，版面改上到下三層（banner / WORK / JOBS），WORK 支援滑鼠雙擊觸發 swap。前提成立：單人 + cortex headless 派工，pane 內無 agent 互動，無他人 client 在看其他 session——「swap 過去看」取代「preview 遠端偷看」沒有副作用。

**swap 可靠性已實測**（tmux 3.4，2026-07-22）：兩個 detached 測試 session（80×24 vs 120×40）跨 session `swap-pane` 600 次，0 失敗、共 1132ms（~1.9ms/次）、pane 數守恆、layout checksum 正常、server 回應正常。原理上 `swap-pane` 是 layout tree 的 O(1) 節點互換，不建立不銷毀狀態，無累積損壞向量。真正的退化是**語意漂移**：奇數次 swap 後 pane 永久留在對方 session（實測確認），故納入 restore-before-swap（§4）把漂移收斂為有界。

## 2. S1 — 版面與移除 DETAIL

- `compose()`（`paulshaclaw/cockpit/app.py:282`）拿掉 `Horizontal(#main-row)` 與左右 `Vertical`，改直排：`Header` → `#brand-banner` → `#work-list` → `#global-jobs` → `Footer`。
- 刪 `#pane-detail` widget 與 `_refresh_widgets` 的 detail 渲染段（`app.py:714-750`）。
- **連根拔 preview 鏈**：`_selected_preview`、建構參數 `preview_loader`、`tmux.py` 的 `capture_preview`、`list_panes` 的 `capture_previews` 分流、`_loader_accepts_capture_previews` 內省 hack 全刪。refresh tick 從此永遠只有一次 `list-panes`（+ 標題缺失 minicom pane 的小 `ps`）。
- 訊息不遺失：degraded 警示 WORK 副標已有（`format_work_pane_subtitle` 的 ⚠）；per-pane job 狀態已在 WORK 列尾綴（`_pane_status`）。DETAIL 底部 `state:` 行與 metadata 行隨 widget 消失，不另遷。
- **tcss（數字釘死）**：
  - `#work-list { height: 1fr; min-height: 5; }` —— 極小終端時 WORK 至少保 5 行，JOBS 從底部先被裁切（Textual layout 自然行為，接受）。
  - `#global-jobs { height: auto; max-height: 12; overflow-y: auto; }` —— 內容列數已有既有 `rows[:10]` 上限（`_refresh_jobs_panel`），10 內容行 + 2 邊框 = 12，正常情況 overflow 不會觸發；`overflow-y: auto` 為保險帶。`max-height` / `min-height` / `overflow` 皆為 textual 0.61.1 已支援屬性（`css/styles.py:120-280` 驗證）。

## 3. S2 — 滑鼠雙擊 swap

### 3.1 已驗證的事件面（textual 0.61.1 原始碼逐條佐證，非推測）

- **點擊鏈**：每次實體點擊 ListItem（含已 highlighted 的列）都走 `ListItem._on_click` post `_ChildClicked`（`widgets/_list_item.py:55`）→ `ListView._on_list_item__child_clicked`（`widgets/_list_view.py:299`）`event.stop()` + 設 `index`（`:302`）+ post 公開事件 `ListView.Selected`（`:303`）。⇒ 第二擊必有可攔截事件，全程公開 API。
- **`Selected` producer 證據（分層宣稱，設計不依賴窮舉）**：(a) textual 層——`_list_view.py` 全檔僅兩處 post `Selected`：`:273`（`action_select_cursor`，即 Enter binding 的 action）與 `:303`（滑鼠點擊鏈），原始碼層窮舉。(b) repo 層——`grep -rnE "select_cursor|list_view_selected|ListView\.Selected" paulshaclaw/ tests/ --include="*.py"` 零命中（exit 1，2026-07-22 實跑）；此為**字面掃描**，僅排除字面呼叫形式，alias／`getattr`／動態建構不在其涵蓋範圍（repo 亦無此類動態呼叫慣例）。(c) **設計層兜底——不依賴 (a)(b) 的窮舉性，且涵蓋任意事件數**：未知 producer 的 `Selected` 事件序列與等量滑鼠點擊序列在 handler 中不可區分、同構處理（逐事件受 ownership guard、手勢中斷語意、0.4s 窗與 `_background_actions_blocked` 約束）。兜底宣稱不是「無法觸發動作」而是「**無法超出既有動作面**」：N 個未知事件至多造成等同 N 次滑鼠點擊的效果——含兩事件成雙擊觸發一次 candidate swap——而 candidate swap 本就是使用者單獨可觸發、且受 restore-before-swap 歸位的動作；不存在狀態毀損或逾越使用者動作面的新失效模式。**本設計新增的因果邊及其接受**：本設計確實新增一條因果邊——「同 pane 兩個 `Selected` 相隔 <0.4s → 一次 candidate swap」；這條邊即雙擊功能的定義本身，移除它等於移除功能，任何 GUI 的雙擊功能皆具此性質。其含意：假想的「意外訊息重複」類故障（非惡意、無任意程式碼能力）會被此邊升級為一次 layout 變動。**明文接受**：升級後的效果仍是單次、可逆、受歸位機制保護的 candidate swap（影響分析同 §3.2 排隊壓縮條），且 (a)(b) 證據顯示現系統無任何已知的非滑鼠 producer——此為「已列管殘餘風險」（§8），非未處置缺口。至於高速惡意 producer 的頻率風險：能在 process 內發送訊息者同樣能直接呼叫 action 或執行任意程式碼，屬 message-driven app 的一般性質、非本設計新增或惡化。⇒ 覆寫鍵盤 producer 後（§3.2），已知路徑中 `Selected` 唯一來源＝滑鼠點擊，未知路徑的效果由設計收斂於既有動作面內。
- **`Highlighted` 先於 `Selected` 入列**：`:302` 的 `index` 賦值同步觸發 `watch_index`（`:166-180`）post `Highlighted`（`:178`），先於 `:303` 的 `Selected` 入列 ⇒ app 的 `on_list_view_highlighted`（同步 `state.set_selection`）必在 `on_list_view_selected` 之前處理。另設 mismatch guard 兜底（§3.2）。
- **binding 優先序**：`Screen._binding_chain`（`screen.py:298-299`）以 `focused.ancestors_with_self` 建鏈——focused widget 最前、app 最後；同鍵合併時先入者勝、非 priority 不覆蓋（`screen.py:332-341`）。⇒ ListView focused 時其 `enter` binding 先於 app 的 `enter` binding 消費。
- **`Click` 無 `chain` 屬性**（0.61 原始碼 grep 確認），手動計時是唯一解；升版 textual 風險大於收益，不升。
- `Selected` message 攜帶 `.list_view` 與 `.item` 欄位（`_list_view.py` Selected 類別定義），支撐 §3.2 的 ownership guard。

### 3.2 設計：鍵盤路徑不產生 `Selected`，`Selected` 成為純滑鼠訊號

- 新增 `WorkListView(ListView)`，**覆寫公開 action method `action_select_cursor`**：不 post `Selected`，直接委派 `self.app.action_swap_selected()`。效果：Enter（由 ListView 自身 binding 消費，§3.1 優先序佐證）→ 直達既有 swap action；鍵盤路徑從此不產生 `Selected`。不用 namespace 字串綁定、不覆寫任何私有方法。
- 同步**移除** `app.on_key` 的 enter 特判（`app.py:582-595`）。app 級 `BINDINGS` 的 `Binding("enter", "swap_selected", ...)` 保留：footer 顯示用＋ListView 未 focus 時的後援；兩路互斥（focused 時 chain 首中即止），同一 action、不會疊加雙發，並以 Pilot「恰好一次」測試回歸守門（§7）。
- 雙擊偵測（app 層 `on_list_view_selected`，即純滑鼠訊號）：
  - **ownership guard 與手勢中斷語意**：`event.list_view.id != "work-list"` → 完全忽略、不碰任何狀態。`event.list_view` 是 work-list 但 `getattr(event.item, "pane_id", None)` 為 None，或點的是 ACTIVE 列 → **清空 `_last_click`**（視為手勢中斷：兩次配對點擊必須「連續」，中間插入無效點擊即重置）。pane_id 由 ListItem 建構時附掛（`WorkItem.pane_id`）。
  - **手勢連續性範圍＝work-list 本地事件流**（明定）：非 work-list 的 `Selected` 不中斷手勢。此定義與「全域點擊流」定義在現有 UI 下**可證等價**——cockpit 套件無任何子目錄（`find paulshaclaw/cockpit -type d` 僅套件根，2026-07-22 驗證），裸字遞迴掃描 `grep -rn "ListView" paulshaclaw/cockpit/ --include="*.py"`（裸字不受實例化語法、subclass 命名影響）共 6 個命中、全在 `app.py`：import（`:14`）、textual 缺席 stub 類別定義（`:60`）、唯一實例化 `yield ListView(id="work-list")`（`:287`）、三處 `query_one("#work-list")` 引用（`:310`/`:414`/`:704`）——全部指向同一個 work-list；modal 場景另有 `_background_actions_blocked` 攔截＋開啟時清空 `_last_click` 雙重保險。不存在能產生非 work-list `Selected` 的畫面元件。**此前提另以 §7 的 runtime 不變量測試機械守護**（靜態掃描僅為當下佐證，不承擔長期完備性）。**設計註記**：未來若新增第二個 ListView，此語意（不中斷 vs 中斷）需重新裁決。
  - 狀態：`_last_click: tuple[str, float] | None`＝`(pane_id, clock())`。**以 pane_id 為 key，不用 row index**——兩擊之間 WORK refresh/reorder 也不會誤配對。
  - 判定：同 pane_id 且 `clock() - last < 0.4s` → **mismatch guard**：驗 `state.selected_pane` 與 `event.item.pane_id` 一致（§3.1 順序佐證下應恆真；不符則降級為新首擊，fail-safe）→ 一致才呼叫既有 `action_swap_selected`（與 Enter 完全同路，含 `_background_actions_blocked` 攔截、swap 後 re-scan）。
  - 不合條件（首擊、逾時、跨列）→ 記為新首擊。ACTIVE 列（pane_id == active pane）：清空 `_last_click`（前點手勢中斷語意）、不觸發。空清單：無事件可發，天然 no-op。
  - `clock` 為可注入參數（預設 `time.monotonic`）→ 計時單測全確定性，不 sleep。
- **`_last_click` 清理點單一化**：`action_swap_selected` 執行時（不論由 Enter、雙擊或未來任何來源觸發）一律先清空 `_last_click`；modal 開啟 action 亦清空；其餘靠 0.4s 逾時自然淘汰。⇒ Enter 與計時器的互動不再依賴「隨後逾時」，而是主動清除（回應 round 2 PARTIAL）。
- **已知並接受的 UX 成本**：cockpit pane 未 focus 時，首次實體點擊被 tmux 拿去 focus pane（不進 app），完成一次雙擊 swap 需至多 3 次實體點擊。不做 workaround。
- **點擊事件排隊壓縮（明文接受的殘餘風險，無兜底機制）**：計時取樣在 handler 執行時而非事件發生時，取樣間隔誤差上界＝事件迴圈單次最大阻塞時間。本 app 同步 handler 的阻塞為 swap（實測 ~2-5ms）、`list-panes` 單次 fork（~10ms 級）、`/proc` 讀（sub-ms）、`read_status` 檔案讀（ms 級）——皆為**典型量測值而非硬上限**（subprocess 無 timeout 保證）。mismatch guard 對此無效（同 pane 兩次慢擊壓縮後 selection 仍一致）。**失效模式影響分析**：唯一錯誤結果是「同一 pane 兩次慢擊被誤判為雙擊」→ 一次非預期 swap，作用對象正是使用者連點的那個 pane；在 `_displacement` 追蹤有效的正常情形下，下一次 activate 因 restore-before-swap 歸位——影響小、可逆。若該 swap 恰逢 §4.3 所列任一脫離追蹤情境（該節為唯一權威清單，此處不重複列舉以免脫節），則與其他錯位一樣計入殘留預算，不另行加碼。以此為據接受，不加 hard timeout 或事件時間戳機制（§8 殘餘風險列管）。

## 4. S3 — restore-before-swap（自動歸位）

### 4.1 狀態與序列化

- app 層唯一欄位：`_displacement: tuple[str, str] | None`＝`(occupant_pane_id 現任佔 slot 者, displaced_pane_id 被擠出去者)`。初始化 `None`。
- **變更點窮舉**（共四處，全部位於 §4.2 的 activate 序列內）：restore 成功（→None）、restore 失敗中止（→None）、liveness 丟棄（→None）、主 swap 成功（→新 pair）。單執行緒下 activate 序列不可分割，無中間態暴露。
- **序列化機制＝Textual 單執行緒事件迴圈**：所有 swap 動作（Enter action、雙擊 handler）都在 message handler 內同步執行（`subprocess.run` 阻塞式），下一個輸入事件必然排在其後——不存在並行交錯，不需另設 in-flight guard。

### 4.2 activate(C) 演算法（含全部終點）

前置：C 必屬 candidate_section（其建構已排除 active pane），且 ACTIVE 列在 §3.2 不記不觸發 ⇒ **C == occupant_pane_id 不可能發生**，無自我 swap 路徑之一。

```
1. 若 _displacement = (occupant, displaced) 存在：
   a. 兩個 pane_id 都在最新 state.panes 快照 → 嘗試 restore swap（occupant ↔ displaced）
      - 成功 → _displacement = None
        · 若 C == displaced → activate 已完成：C 此刻已在 active slot，且 slot 即其原位，
          零錯位。跳過主 swap。                                【終點 A】
        · 否則 → 繼續 2.
      - 失敗（CalledProcessError，含快照後才死的 TOCTOU）→ _displacement = None、
        notify 警示、**中止本次 activate（不做主 swap）**。      【終點 B】
        重試語意：下一次 activate 因記錄已空，即為乾淨的 plain swap。
   b. 任一不在快照（現任死／被擠者死／皆死，三情形同一處理：歸位不可成立）
      → _displacement = None（丟棄，不 notify——pane 關閉是日常操作），繼續 2.
2. 嘗試主 swap（active slot 現內容 ↔ C）
   - 成功 → _displacement = (C, 此刻被擠出者)                   【終點 C】
   - 失敗（CalledProcessError）→ _displacement 維持 None、notify 【終點 D】
3. 所有終點（A/B/C/D）一律接既有 _reconcile_state() 全量 re-scan。
```

- 終點 A 消除 round 2 指出的 `C == displaced` 自我 swap（`A ↔ A`）與 `(A, A)` 髒記錄。
- 終點 B 消除「restore 失敗仍疊加新位移」：失敗後不做主 swap，同一 activate 內絕不產生第二對錯位；該次失敗遺下的一對成為脫離追蹤殘留（§4.3），且已 notify 操作者。
- 「restore 成功但主 swap 失敗」（終點 D 經 1a 成功路徑）落點：`None` 且實際零錯位——狀態與現實一致。
- 錯誤回報沿用既有 `notify` 路徑（`_after_manager_tick` 同款，fail-soft 不 crash）。

### 4.3 追蹤語意與殘留（誠實版）

- **不變量（無條件成立）**：cockpit **追蹤中**的錯位任何時刻至多一筆（`_displacement` 單槽，變更點窮舉於 §4.1）；且單次 activate 至多產生一對新錯位（終點 B 保證失敗時為零）。
- **脫離追蹤的殘留**來源與上限：(a) restore 失敗（終點 B）每次至多遺下一對——觸發條件罕見（快照後 pane 才死、tmux server 異常），且已 notify；(b) process 結束時未歸位的至多一對；(c) liveness 丟棄（§4.2 1.b，追蹤中 pane 死亡）每次至多一對——雖一端已消失，存活端仍可能不在原位（如被擠者死時現任長駐 slot），此殘留同樣脫離追蹤。跨 lifetime 累積上限 = restore 失敗次數 + liveness 丟棄次數 + 重啟次數。
- **明文接受**：單人環境下脫離追蹤殘留靠操作者手動 swap 回或關 pane 收拾；不做持久化、不做啟動時修復、不設手動歸位鍵（決策記錄：使用者選「自動歸位、in-memory、重啟歸零」）。
- pane 以 `%id` 定址（tmux pane id 終身穩定不重用），與位置、session 歸屬無關。
- 分層不變：`actions.py`（`LayoutActionService`）維持無狀態純 tmux 指令層；`_displacement` 與 activate 序列在 app/state 層，以 fake actions 錄呼叫序單測。

## 5. S4 — JOBS 收合

- `j` binding toggle，預設展開，收合狀態 in-memory 不持久化。modal 開啟時循 `_background_actions_blocked` 攔截。
- 展開態：§2 的 `height: auto; max-height: 12`。
- 收合態：內容清空、`styles.max_height = 3`（上邊框 + 空內容行 + 下邊框），border title 改 `JOBS ▸ N slices`（N 照常隨 refresh 刷新；展開時 title 為 `JOBS`、副標 `N slices` 維持現制）。
- 驗收數字：展開高度 = `min(2 + 內容行數, 12)`；收合高度 ≤ 3。

## 6. spec delta 與需求對照表

來源：`openspec/specs/stage11-operator-cockpit/spec.md`。下表逐條列出該檔**全部 8 條** `### Requirement:` 標題原文與處置；propose 階段以 openspec 對該檔 diff 驗證本表無遺漏（本文件單獨閱讀時的完備性以該機制封閉）。

| # | 既有 requirement（標題原文） | 處置 |
|---|---|---|
| 1 | Cockpit lists panes from all local tmux sessions | **修改**：刪去欄位列表中的「preview data needed by the existing cockpit UI」，其餘保留 |
| 2 | Work list remains flat and identifies pane origin | 保留 |
| 3 | Active slot selection is scoped to the cockpit session | 保留 |
| 4 | Active-slot refresh ignores matching geometry in other sessions | 保留 |
| 5 | Candidate section includes all non-cockpit non-active panes | **修改（truth-up）**：#249「WORK 收斂自身 session」已出貨（`store.py:102` 過濾 `session_name == cockpit_session_name`）但 spec 文字未同步——本 delta 把候選範圍修正為 cockpit session、他 session 僅入枚舉與 banner 統計（plan 審查 round 1 揭露之既有漂移） |
| 6 | Enter swaps selected pane with active slot across sessions | **修改**：Enter 與 double-click 雙 trigger、行為等價；Enter 路徑收斂為 WorkListView `action_select_cursor` 覆寫＋app binding 後援的單一 action 權威（§3.2）；並納入 restore-before-swap 前置序列（§4.2） |
| 7 | Startup fails when cockpit pane cannot identify its session | 保留 |
| 8 | Cockpit provides footer and modal hotkey help | **修改**：footer/modal 納入 `j` 與雙擊說明 |

新增 requirement：三層直排版面（banner/WORK/JOBS）＋ 移除 DETAIL（§2）；restore-before-swap（§4.2 演算法含終點 A/B + §4.3 追蹤語意）；JOBS 收合（§5 驗收數字）。

## 7. 測試計畫

- **刪**：detail/preview 相關單測（`_selected_preview`、capture_preview、detail 渲染）。
- **雙擊（單測，注入 clock）**：命中（<0.4s 同 pane_id）；逾時不觸發；跨列不觸發且重記首擊；成功後清空（三擊＝新首擊）；modal 開啟時被攔；**ownership guard**（`list_view.id` 非 work-list → 忽略且不碰狀態；work-list item 無 pane_id → 清空 `_last_click`）；**手勢中斷**（click C → click ACTIVE → click C 皆 <0.4s → 不觸發 swap，第三擊為新首擊）；**手勢連續性範圍鎖定**（click C → 合成非 work-list `Selected` → click C 皆 <0.4s → 仍配對觸發 swap，鎖定 WORK-local 語意）；**mismatch guard**（`state.selected_pane` 與 item 不符 → 降級新首擊）。
- **Enter 單一權威（Pilot 整合測試）**：ListView focused 按 Enter → fake actions 收到**恰好一次** swap（防覆寫路徑與 app binding 雙發回歸）；Enter 觸發後 `_last_click` 已清空（先點一下再按 Enter，再點一下不得誤判雙擊）。
- **雙擊事件鏈（Pilot 整合測試）**：`pilot.click` 同列兩次（注入 clock 控制間隔）→ fake actions 收到 swap——直接驗證 `ListView → Selected → handler → action` 實鏈，同時充當 textual 升版守門（`Selected`-on-click 語意改變即紅燈）。
- **restore（fake actions 錄呼叫序）**：happy path（restore→main 兩次 swap、記錄輪替）；被擠者死→跳 restore 直接 main；現任死→同；**C == displaced →恰好一次 swap（restore），無 `A↔A` 呼叫、記錄 None**（終點 A）；**restore 拋錯→恰好一次 swap 嘗試、無主 swap、記錄 None、notify**（終點 B），且下一次 activate 為乾淨 plain swap；**組合分支：C == displaced 且 restore 拋錯→走終點 B（恰好一次 swap 嘗試、無主 swap、無 self-swap、記錄 None、notify）**；main 拋錯→記錄 None+notify（終點 D）；連續 activate 三個 pane 的記錄輪替。
- **JOBS**：toggle 展開/收合高度斷言（`run_test` 量 region 高度：展開 = min(2+rows,12)、收合 ≤3）；收合時 title 的 N 隨 refresh 更新；`j` 在 modal 開啟時無效。
- **版面**：三層順序存在、`#pane-detail` 不存在、極小終端（如 80×15）WORK ≥5 行。
- **唯一 ListView 不變量（run_test，多檢查點）**：`app.query(ListView)` 恰含一個實例且其 `id == "work-list"`（subclass 亦被 `query(ListView)` 匹配，與 WorkListView 相容），於下列已枚舉畫面狀態逐一斷言：mount 完成後、help modal 開啟時與關閉後、manager modal 開啟時與關閉後、一次 refresh tick 後。**守護範圍誠實界定**：此測試對「已枚舉狀態集合」提供機械回歸防護；對未來「條件性／延遲建立」的 ListView 屬全稱命題，測試無法窮舉，該部分由 §3.2 設計註記（新增 ListView 需重裁決手勢語意）的 code review 慣例承擔——測試是強力早警，不是全稱保證。

## 8. 殘餘風險（已收斂）

1. ~~Textual 0.61 雙擊事件序~~ → 原始碼逐條佐證（§3.1：producer 窮舉、入列順序、binding 優先序），Pilot 實鏈測試守門。
2. ~~restore 半失效呼叫序~~ → §4.2 終點 A-D 全路徑定義（含 `C == displaced` 與失敗中止）；§4.3 追蹤語意無條件不變量。
3. ~~tcss auto+max-height~~ → 屬性支援已驗證、數字釘死（§2）、run_test 高度斷言驗收（§7）。
4. WSL2 + Windows Terminal + tmux 滑鼠轉發鏈：影響的是「點擊是否到達 app」（現況滑鼠選取已在用、`mouse on` 已開），非本設計新增面；若環境不轉發，鍵盤路徑完整可用——降級安全。
5. **點擊排隊壓縮（接受、列管）**：事件迴圈阻塞無硬上限，極端阻塞下同 pane 兩次慢擊可能被誤判為雙擊。影響：一次非預期 swap（對象即使用者連點的 pane）；`_displacement` 追蹤有效時下一次 activate 歸位，恰逢脫離追蹤情境則計入 §4.3 殘留預算（與 §3.2 影響分析同一措辭）。不設 hard timeout／事件時間戳。
6. **`Selected×2 → swap` 因果邊（接受、列管）**：雙擊功能定義本身；假想「意外訊息重複」故障會被升級為一次可逆、受歸位保護的 candidate swap（§3.1(c) 影響分析）。現系統無已知非滑鼠 producer（textual 原始碼窮舉＋repo 掃描），發生前提是未來引入重複發送 `Selected` 的缺陷程式碼。
