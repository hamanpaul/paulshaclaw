---
dispatch: hold
slice_id: cockpit-three-layer
plan: null
depends_on: []
---

# Cockpit 三層直排 + 雙擊 swap + 自動歸位 設計

> 日期：2026-07-22 ｜ 狀態：修訂 v2（回應 codex 對抗審查 round 1，待重審）｜ 分支：`feature/cockpit-three-layer`
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

### 3.1 已驗證的事件面（textual 0.61.1 原始碼，非推測）

- 每次實體點擊 ListItem（**含已 highlighted 的列**）都走：`ListItem._on_click` post `_ChildClicked`（`widgets/_list_item.py:55`）→ `ListView._on_list_item__child_clicked`（`widgets/_list_view.py:299`）`event.stop()` + 設 index + **post 公開事件 `ListView.Selected`**。⇒ 第二擊必有可攔截事件，且全程公開 API。
- **埋伏**：ListView 自帶 `Binding("enter", "select_cursor")`（`_list_view.py:29`），Enter 也會 post `Selected`。若直接拿 `Selected` 餵雙擊計時器，會與 app 現有 `on_key` enter 路徑（`app.py:582-595`）疊加造成 double-swap。
- `Click` 事件在 0.61 無 `chain` 屬性（原始碼 grep 確認），手動計時是唯一解；升版 textual 風險大於收益，不升。

### 3.2 設計：讓 `Selected` 成為「純滑鼠」訊號

- 新增 `WorkListView(ListView)` subclass（公開 API，僅覆寫 `BINDINGS`）：把 `enter` 重綁為 `app.swap_selected`（namespace binding 直達既有 action）。效果：鍵盤 Enter 不再經 `select_cursor`、**不再 post `Selected`**；`Selected` 從此只由滑鼠點擊產生。
- 同步**移除** `app.on_key` 的 enter 特判（`app.py:582-595`）——單一權威路徑，杜絕雙發。app 級 `BINDINGS` 的 `Binding("enter", ...)` 保留（footer 顯示用；ListView focused 時由 WorkListView binding 先消費，不會同鍵雙發）。
- 雙擊偵測（app 層 `on_list_view_selected`）：
  - 狀態：`_last_click: tuple[str, float] | None`＝`(pane_id, clock())`。**以 pane_id 為 key，不用 row index**——兩擊之間 WORK refresh/reorder 也不會誤配對。pane_id 由 ListItem 建構時附掛（`WorkItem.pane_id` 屬性），從 `Selected.item` 直讀。
  - 判定：同 pane_id 且 `clock() - last < 0.4s` → 呼叫既有 `action_swap_selected`（與 Enter 完全同路，含 `_background_actions_blocked` 攔截、swap 後 re-scan），**成功觸發後清空 `_last_click`**（三擊＝新循環的第一擊）。
  - 不合條件（首擊、逾時、跨列）→ 記為新首擊。ACTIVE 列（pane_id == active pane）與空清單：不記、不觸發。
  - `clock` 為可注入參數（預設 `time.monotonic`）→ 計時單測全確定性，不 sleep。
- 狀態失效規則：任何 modal 開啟（help/manager）→ `action_swap_selected` 本已被 `_background_actions_blocked` 擋下，另於 modal 開啟 action 中清空 `_last_click`；0.4s 逾時自然淘汰 stale 首擊（focus loss 無需特別處理——沒有懸掛 callback，`_last_click` 是被動資料，無 teardown 取消問題）。
- Enter 與計時器互動：Enter 不經 `Selected`（§3.2 第一點），**與 click timer 完全無交互**——首擊後按 Enter 就是普通 Enter swap，`_last_click` 隨後逾時作廢。
- **已知並接受的 UX 成本**：cockpit pane 未 focus 時，首次實體點擊被 tmux 拿去 focus pane（不進 app），此時完成一次雙擊 swap 需至多 3 次實體點擊。不做 workaround（tmux 正常行為；cockpit 常駐 focused 是主要使用型態）。
- 點擊事件排隊壓縮：計時取樣在 handler 執行時而非事件發生時，若前一 handler 阻塞 >0.4s 可能把兩次慢擊壓成雙擊——swap 實測 ~2-5ms，阻塞窗遠小於閾值，接受不處理。

## 4. S3 — restore-before-swap（自動歸位）

### 4.1 狀態與序列化

- app 層唯一欄位：`_displacement: tuple[str, str] | None`＝`(occupant_pane_id 現任佔 slot 者, displaced_pane_id 被擠出去者)`。初始化 `None`；只在 §4.2 定義的兩個 commit 點變更，絕無中間態暴露。
- **序列化機制＝Textual 單執行緒事件迴圈**：所有 swap 動作（Enter action、雙擊 handler）都在 message handler 內同步執行（`subprocess.run` 阻塞式），下一個輸入事件必然排在其後——不存在並行交錯，不需另設 in-flight guard。此為設計依據，明文記錄。

### 4.2 activate(C) 演算法（含 commit 點與失敗路徑）

```
1. 若 _displacement 存在：
   a. 兩個 pane_id 都在最新 state.panes 快照 → 嘗試 restore swap（現任 ↔ 被擠者）
      - 成功 → _displacement = None                    【commit 點 1】
      - 失敗（CalledProcessError，含快照後才死的 TOCTOU）→ _displacement = None、
        notify 警示、繼續往 2.（fail-soft，restore 放棄不重試）
   b. 任一不在快照（現任死／被擠者死／皆死，三情形同一處理：沒有可成立的歸位）
      → _displacement = None（丟棄，不 notify——pane 關閉是日常操作）
2. 嘗試主 swap（active slot 現內容 ↔ C）
   - 成功 → _displacement = (C, 此刻被擠出者)          【commit 點 2】
   - 失敗（CalledProcessError）→ _displacement 維持 None、notify 警示
3. 無論成敗 → 既有 _reconcile_state() 全量 re-scan（swap 後重掃是既有行為）
```

- 「restore 成功但主 swap 失敗」落點：`_displacement = None` 且實際零錯位——**狀態與現實一致**，非中間態。
- 「restore 失敗」落點：`None` + 現實可能殘留一對錯位——與重啟殘留同類（§4.3），計入殘留預算。
- 錯誤回報沿用既有 `notify` 路徑（`_after_manager_tick` 同款，fail-soft 不 crash）。

### 4.3 不變量（誠實版）與殘留

- **不變量**：同一次 cockpit process 生命週期內、無 swap 失敗的前提下，由 cockpit 觸發的錯位任何時刻至多一對。
- **殘留來源**：process 結束時未歸位的最後一對、以及 restore 失敗放棄的錯位。跨多次重啟殘留可累積（每 lifetime 至多貢獻一對）。**明文接受**：單人環境下靠操作者手動 swap 回或關 pane 收拾；不做持久化、不做啟動時修復、不設手動歸位鍵（決策記錄：使用者選「自動歸位、in-memory、重啟歸零」）。
- pane 以 `%id` 定址（tmux pane id 終身穩定不重用），與位置、session 歸屬無關。
- 分層不變：`actions.py`（`LayoutActionService`）維持無狀態純 tmux 指令層；`_displacement` 與 activate 序列在 app/state 層，以 fake actions 錄呼叫序單測。

## 5. S4 — JOBS 收合

- `j` binding toggle，預設展開，收合狀態 in-memory 不持久化。modal 開啟時循 `_background_actions_blocked` 攔截。
- 展開態：§2 的 `height: auto; max-height: 12`。
- 收合態：內容清空、`styles.max_height = 3`（上邊框 + 空內容行 + 下邊框），border title 改 `JOBS ▸ N slices`（N 照常隨 refresh 刷新；展開時 title 為 `JOBS`、副標 `N slices` 維持現制）。
- 驗收數字：展開高度 = `min(2 + 內容行數, 12)`；收合高度 ≤ 3。

## 6. spec delta 與需求對照表

stage11-operator-cockpit 既有 requirement 逐條處置：

| 既有 requirement | 處置 |
|---|---|
| 全 session pane 枚舉（含 preview data 欄位） | **修改**：刪去「preview data」欄位要求，其餘保留 |
| 扁平 work list + `session:window` 標示 | 保留 |
| active slot 限 cockpit session | 保留 |
| anchor 幾何 reconcile 兩條 | 保留 |
| candidate section 排序 | 保留 |
| 「Enter 為唯一 swap trigger」 | **修改**：Enter 與 double-click 雙 trigger、行為等價；Enter 路徑收斂為 WorkListView binding 單一權威 |
| 缺 cockpit pane 啟動失敗 | 保留 |
| footer/modal 說明 | **修改**：納入 `j` 與雙擊的說明 |

新增 requirement：三層直排版面（banner/WORK/JOBS）＋ 移除 DETAIL；restore-before-swap（§4.2 演算法 + §4.3 不變量措辭）；JOBS 收合（§5 驗收數字）。

## 7. 測試計畫

- **刪**：detail/preview 相關單測（`_selected_preview`、capture_preview、detail 渲染）。
- **雙擊（單測，注入 clock）**：命中（<0.4s 同 pane_id）；逾時不觸發；跨列不觸發且重記首擊；ACTIVE 列不記；成功後清空（三擊＝新首擊）；modal 開啟時被攔。
- **Enter 單一權威（Pilot 整合測試）**：ListView focused 按 Enter → fake actions 收到 **恰好一次** swap（防 WorkListView binding 與殘留路徑雙發回歸）。
- **雙擊事件鏈（Pilot 整合測試）**：`pilot.click` 同列兩次（注入 clock 控制間隔）→ fake actions 收到 swap——直接驗證 `ListView → Selected → handler → action` 實鏈，同時充當 textual 升版守門（`Selected`-on-click 語意改變即紅燈）。
- **restore（fake actions 錄呼叫序）**：happy path（restore→main 兩次 swap、記錄更新）；被擠者死→跳 restore 直接 main；現任死→同；restore 拋錯→記錄清空+main 照做+notify；main 拋錯→記錄 None+notify；連續 activate 三個 pane 的記錄輪替。
- **JOBS**：toggle 展開/收合高度斷言（`run_test` 量 region 高度：展開 = min(2+rows,12)、收合 ≤3）；收合時 title 的 N 隨 refresh 更新；`j` 在 modal 開啟時無效。
- **版面**：三層順序存在、`#pane-detail` 不存在、極小終端（如 80×15）WORK ≥5 行。

## 8. 殘餘風險（已收斂）

1. ~~Textual 0.61 雙擊事件序~~ → 已從原始碼驗證（§3.1），並以 Pilot 實鏈測試守門。
2. ~~restore 半失效呼叫序~~ → §4.2 演算法定義全部失敗路徑與 commit 點；§4.3 誠實化不變量。
3. ~~tcss auto+max-height~~ → 屬性支援已驗證、數字釘死（§2）、run_test 高度斷言驗收（§7）。
4. WSL2 + Windows Terminal + tmux 滑鼠轉發鏈：影響的是「點擊是否到達 app」（現況滑鼠選取已在用、`mouse on` 已開），非本設計新增面；若環境不轉發，鍵盤路徑完整可用——降級安全。
