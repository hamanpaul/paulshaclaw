# Stage 11 Operator Cockpit — Design

- Date: 2026-04-22
- Status: proposed
- Owner: @hamanpaul
- Topic: 新增 Stage 11，提供真正的 interactive terminal UI，作為 tmux pane fleet 與 job state 的 operator cockpit

## 0. 背景

目前 Stage 1 的 `tui` 實作只有 deterministic 的純文字 renderer，責任是把設定中的 pane/task 映射輸出成表格。這符合 Stage 1 baseline，但不符合本專案對「interactive TUI」的預期。

本次設計明確把「真正可操作的 terminal UI」拆成新的 **Stage 11**，不回頭擴張 Stage 1 責任，也不改寫 Stage 3 的 lifecycle / job canonical contract。Stage 11 的角色是提供一個 operator cockpit，讓使用者把整個 tmux 環境視為一體化 UI 來觀察與調度。

## 1. 目標與非目標

### 1.1 目標

- 提供一個真正可互動的 terminal UI，作為 tmux pane fleet 的控制平面
- 將 `%0` 類似 pane 視為 cockpit 本體，其餘非 TUI panes 視為可被觀察與調度的工作區
- 支援 read-mostly MVP：pane list、active slot、selected pane detail、global jobs 與 selected pane jobs
- 支援最小 layout mutation：選取 pane 後按 `Enter`，將該 pane 與 active slot 互換
- 將 pane 即時狀態與 job artifact 狀態以 hybrid 方式合併顯示

### 1.2 非目標

- 不修改 Stage 1 的 `render_pane_task_view()` baseline contract
- 不重定義 Stage 3 lifecycle、trace、registry 或 coordinator 的 canonical schema
- 第一版不實作 send message、interrupt、adopt/release、rename、resize、approval flow
- 第一版不要求 pane 與 job 一定能完美對映；允許 best-effort 顯示

## 2. Stage 定位與邊界

Stage 11 是獨立的 `operator cockpit` stage。

- Stage 1：保留 daemon / config / Telegram / text renderer baseline
- Stage 3：保留 lifecycle / job / trace 的 canonical artifact ownership
- Stage 11：擁有 interactive control plane，負責把 tmux pane fleet 與 job state 組成可操作 UI

Stage 11 可以讀：

- tmux 即時狀態
- registry / coordinator state
- Stage 3 lifecycle artifacts

Stage 11 可以寫：

- layout action，例如 `swap-pane`
- 自身需要的 UI-local state

Stage 11 不直接改寫 Stage 1 / Stage 3 的資料契約，也不把自己變成新的 canonical source of truth。

## 3. 核心設計原則

### 3.1 tmux as the real UI surface

這個 stage 的關鍵不是在自己的視窗內做一個 isolated preview app，而是承認「整個 tmux layout 就是 UI 本體」。Cockpit 只是一個控制與觀測面，用來操控其他 panes 的配置與內容切換。

### 3.2 Pane-first, not chat-first

Stage 11 不是聊天殼，也不是單純 job dashboard。它的主軸是：

- pane fleet 觀察
- active work slot orchestration
- pane 與 job state 的聯動檢視

### 3.3 Read-mostly MVP

第一版以觀測與安全的 layout orchestration 為主。只允許一種 mutation：`swap selected pane with active slot`。其他動作留待後續 stage 或 Stage 11 的後續迭代。

## 4. UI 與互動模型

### 4.1 主畫面結構

第一版固定成四塊：

1. `Active Slot`
   顯示專用工作窗的 pane id、title、command、size、狀態
2. `Work List`
   列出所有非 TUI pane；其中 `ACTIVE` pane 放在獨立小節
3. `Pane Detail`
   顯示目前選中 pane 的 snapshot、metadata、對應 job 摘要
4. `Global Jobs`
   顯示全域 job 摘要，例如最近 N 筆、狀態、trace id、對應 pane/agent

### 4.2 Active slot 規則

- 啟動時只判定一次 active slot
- 候選為所有非 TUI pane
- 必須排除 TUI 自己所在 pane
- 若 TUI pane 與其他 pane 面積相同，也必須優先排除 TUI pane
- 預設以最大非 TUI pane 為 active slot
- active slot 不會因 layout 變動自動漂移到新的最大 pane

### 4.3 Work list 規則

- 收錄所有非 TUI panes
- `ACTIVE` pane 顯示在獨立小節
- 其他 pane 顯示在候選小節
- TUI 自己所在 pane 永遠不出現在清單內

### 4.4 互動鍵位

第一版至少需要：

- `Up/Down`：移動 work list selection
- `Enter`：將選中 pane 與 active slot 執行 `swap-pane`
- 回到 cockpit 的明確操作：用來從 active pane 跳回 `%0`

第一版的焦點規則：

- 游標移動不產生外部副作用
- `Enter` 才是真正的 swap trigger
- swap 後預設跳到新換入的 active pane
- 後續可配置為「swap 後留在 cockpit」，但不是 MVP 預設

## 5. Runtime 架構

建議採 `Textual` 實作，並將 Stage 11 拆成三層：

```text
Textual UI
  -> cockpit store/state
    -> adapters/services
       - tmux adapter
       - artifact adapter
       - layout action service
```

### 5.1 Textual UI

負責：

- 畫面 layout
- selection / focus
- keyboard handling
- 顯示 observed state 與 control state

不直接負責：

- 執行 tmux 命令
- 解析 artifacts
- 決定 swap 是否合法

### 5.2 Cockpit store/state

負責把兩類狀態分開：

- `observed state`
  tmux scan、pane metadata、artifact merge 後的事實
- `control state`
  selection、active slot id、focus-return mode、degraded flags

這個切分是為了避免把 UI selection 誤當成 tmux truth。

### 5.3 Adapters / services

- `tmux adapter`
  列 pane、抓 snapshot、讀 pane metadata
- `artifact adapter`
  從 Stage 3 / coordinator / registry 讀 job、trace、agent 對應資訊
- `layout action service`
  執行 `swap-pane`、校驗 self-pane exclusion、swap 後觸發 re-scan

## 6. 資料來源與資料流

Stage 11 採 hybrid 模式。

### 6.1 Pane 狀態

pane 狀態以 tmux 即時掃描為準：

- pane list
- pane size
- pane title / command
- snapshot preview

### 6.2 Job 狀態

job 狀態優先讀：

- Stage 3 lifecycle artifacts
- coordinator state
- registry metadata

若找不到完整映射，允許 best-effort 顯示：

- `unknown`
- `unmapped`
- `no artifact`

### 6.3 匯流模型

```text
tmux list-panes / capture-pane / metadata
    -> tmux adapter
    -> cockpit store
         -> Active Slot / Work List / Pane Detail

stage3 artifacts + coordinator state + registry
    -> artifact adapter
    -> cockpit store
         -> Global Jobs / selected pane job detail
```

pane 面與 job 面是兩條來源不同的管線，只在 cockpit store 匯合，不互相假設另一條一定完整。

## 7. 安全規則與 degraded behavior

### 7.1 唯一 mutation

第一版只允許一種 layout mutation：

- `swap selected pane with active slot`

這條必須在 UI 層與 service 層都受控，不允許隱式 side effect。

### 7.2 Self-pane exclusion

cockpit 自己所在 pane：

- 不可進 work list
- 不可成為 active slot
- 不可成為 swap target

### 7.3 Active slot immutability

active slot 在啟動時只挑一次。若 active slot 消失：

- Stage 11 進入 degraded state
- UI 必須明確標示 active slot lost
- 不可靜默改指向其他 pane
- operator 需明確重新指定或重啟 Stage 11

### 7.4 Post-swap reconciliation

每次 swap 後，必須立即重新掃描 tmux 並重建畫面狀態；不得只靠 UI 端推測結果。

### 7.5 Artifact degradation

若 Stage 3 / coordinator / registry 資料缺失：

- pane 面仍可用
- job 面標記為 degraded / unknown
- 不得因此阻斷 Stage 11 的基本使用

## 8. 測試策略

### 8.1 Unit

覆蓋：

- active slot 選擇
- self-pane exclusion
- work list segmentation
- artifact merge
- selection 與 focus state

### 8.2 Service / integration

使用 fake tmux adapter 或受控輸入驗證：

- swap 規則
- active slot 保持不漂移
- post-swap reconciliation
- degraded handling

### 8.3 End-to-end

在真 tmux session 驗證：

- 啟動時排除 TUI pane
- 正確挑出最大非 TUI pane 當 active slot
- `Enter` 後 active slot 與候選 pane 真的互換
- swap 後焦點預設跳到新的 active pane
- operator 可再回到 cockpit

## 9. MVP 驗收標準

- Stage 11 是獨立 stage，不修改 Stage 1 canonical spec
- cockpit 可在單獨的 tmux pane 中啟動
- 啟動時可從所有非 TUI panes 中選出 active slot
- work list 可列出所有非 TUI panes，並把 `ACTIVE` pane 顯示在獨立小節
- 選中候選 pane 後按 `Enter` 可與 active slot 互換
- swap 後預設跳到新的 active pane
- pane detail 可顯示 selected pane 的 snapshot 與 metadata
- global jobs 區可顯示全域 job 摘要
- selected pane 區可顯示對應 job / trace 摘要；找不到時明確標示 degraded
- Stage 3 artifacts 不完整時，Stage 11 仍能作為 pane cockpit 使用

## 10. 後續擴充方向

這些不在 MVP，但設計上需預留邊界：

- send message / interrupt
- adopt / release
- explicit active-slot reassignment
- mouse support
- richer confirm / approval flows
- more than one dedicated work slot

