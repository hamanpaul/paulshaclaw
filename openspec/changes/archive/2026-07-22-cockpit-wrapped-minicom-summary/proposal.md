## Why

cockpit WORK 面板無法把「經 `serialwrap-minicom` wrapper 啟動的 minicom」辨識為 minicom。serialwrap 的標準用法是透過 wrapper 開 minicom（broker 仲裁單一寫入者、RAW log、多 agent 協調），minicom 因而是 wrapper（bash script）的 child，tmux `#{pane_current_command}` 回報的是 `bash` 而非 `minicom`。`derive_summary` 的 `command == "minicom"` guard 隨之失效，pane 落到 cwd basename fallback，顯示成 `paul_chen` 之類無法辨識的標籤，operator 看不出哪個 pane 是 COM0/COM1 序列主控台。這在本機是結構性問題（只要 minicom 經 serialwrap 開就必中），非偶發。

## What Changes

- `derive_summary(pane)`：當 pane 無有效 title（空或等於 host_short）**且** `command` 是已知 shell（`bash`/`sh`/`zsh`/`dash`/`ash`/`fish`）時，先嘗試 tty-based `_minicom_summary(pane.pane_tty)`（`ps -t` 掃該 tty 上的行程，能穿透 wrapper 找到 minicom argv）；命中回傳 `minicom COMx` 才採用，未命中再退回既有 cwd basename fallback。
- 直跑 minicom（`command == "minicom"`）的既有分支與行為完全不變；非 shell、非 minicom 的 pane 行為不變。
- 成本邊界維持：`_minicom_summary` 為 bounded 1s timeout 的單次 `ps`，只對「無 title 的 shell pane」多跑一次，不影響已有 title 或非 shell pane。

## Capabilities

### New Capabilities
<!-- 無新增 capability -->

### Modified Capabilities
- `stage11-operator-cockpit`: WORK 清單的 pane 標籤衍生新增一條要求——執行 minicom 的 pane（含經 wrapper 間接啟動、tmux 回報 command 為 shell 者）MUST 被標示為其 minicom COM 埠身分，而非退回 cwd basename。

## Impact

- 受影響碼：`paulshaclaw/cockpit/tmux.py`（僅 `derive_summary`）。
- 測試：`tests/test_stage11_operator_cockpit.py` 新增「wrapper 底下 minicom、command==bash 仍標成 `minicom COMx`」與「未命中 minicom 的 shell pane 仍退回 cwd basename」兩案。
- 相依：無新增依賴（沿用既有 `_minicom_summary` / `ps`）。
- 文件：spec delta 於本 change；README/docs 無需同步（純內部 UI 標籤修正，R-18 WARN 可上 `policy-exempt:docs-sync` 或直接免）。
- 非目標：不改 tmux `list-panes -a` 掃描範圍、不改 candidate_section 的 session 收斂（#249）、不動 serialwrap wrapper（架構上 minicom 必為 child，無法單純 exec 取代）。
