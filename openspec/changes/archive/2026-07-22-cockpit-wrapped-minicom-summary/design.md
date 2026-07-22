## Context

`derive_summary(pane)`（`paulshaclaw/cockpit/tmux.py`）決定 WORK 清單每個 pane 的標籤。目前優先序：

1. `title` 非空且 `title != host_short` → 用 `title`
2. 否則 `command == "minicom"` → `_minicom_summary(pane_tty)`（`ps -t <tty>` 掃 minicom argv 取 `COMx`）
3. 否則 `pane_current_path` 非空 → cwd basename
4. 否則 → `[command]`

serialwrap 的標準用法是 `serialwrap-minicom` wrapper（bash script）啟動 minicom，minicom 為 wrapper 的 child，故 tmux `#{pane_current_command}` 回報 `bash`。步驟 2 的 `command == "minicom"` guard 因而永不成立，落到步驟 3 顯示 cwd basename（`paul_chen`）。已驗證：直接對 %3/%4 的 tty 呼叫 `_minicom_summary` 正確回 `minicom COM0`/`COM1`——偵測函式本身能穿透 wrapper，問題純在 guard 擋住它被呼叫。

## Goals / Non-Goals

**Goals:**
- 經 wrapper 啟動的 minicom pane 在 WORK 清單標為 `minicom COMx`。
- 直跑 minicom 與所有非 minicom pane 的既有行為零變化。
- 每次 refresh 的額外成本受控（不對每個 pane 無差別跑 `ps`）。

**Non-Goals:**
- 不改 `_minicom_summary` 的偵測邏輯（已能穿透 wrapper）。
- 不改 tmux 掃描範圍或 `candidate_section` 的 session 收斂（#249）。
- 不改 serialwrap wrapper：`_run_broker_minicom` 需在 minicom 退出後 `console-detach` cleanup（`trap ... EXIT`），minicom 架構上必為 child，無法單純 `exec` 取代。

## Decisions

- **決策：在步驟 2 與步驟 3 之間，對「無 title 的 shell pane」插入一次 tty-based minicom 探測。**
  當 `title` 不可用（空或 == host_short）且 `command` ∈ shell 集合時，先 `_minicom_summary(pane_tty)`；非 None 才用，None 則續走 cwd basename。
  - 為何限「shell command」而非「所有 command」：serialwrap wrapper 是 bash script，tmux 一定回報 shell 名。限縮到 shell 集合可避免對每個 idle pane（如 `node`/`vim`/`claude`）多跑 `ps`，把額外成本鎖在真正可能藏 wrapped-minicom 的 pane。
  - shell 集合：`{bash, sh, zsh, dash, ash, fish}`（涵蓋常見 login/script shell；以純函式常數表示，易擴充與單測）。
  - **替代方案 A（否決）**：對所有非 minicom pane 都跑 `_minicom_summary`——語意最寬但每 refresh 對 N 個 pane 各跑一次 `ps`（各 1s timeout），idle 多 pane 場景成本不可控。
  - **替代方案 B（否決）**：改 serialwrap wrapper 用 `exec minicom`——破壞 detach cleanup（見 Non-Goals），且跨 repo 改動超出本 change scope。
  - **替代方案 C（否決）**：cockpit 端硬編 `serialwrap-minicom` 進程名比對——比 `ps` 掃 minicom argv 更脆（wrapper 改名即失效），且仍要跑 `ps`，無成本優勢。

- **決策：探測命中才覆蓋，未命中透明退回。** 保證非 minicom 的 shell pane（純 idle bash）行為與現況位元相同——只是多一次回傳 None 的 `ps`。

## Risks / Trade-offs

- [無 title 的 idle bash pane 每 refresh 多一次 `ps -t`] → 已由 shell 集合限縮 + `_minicom_summary` 內建 1s timeout + 只在 title 不可用時觸發；`list_panes(capture_previews=False)` 的 refresh 路徑本就避開較貴的 `capture-pane`，單次 `ps` 成本可忽略。
- [shell 集合掛一漏萬（非常見 shell 名的 wrapper）] → 影響僅「該 pane 退回 cwd basename」，非崩潰；集合為常數，日後可加。
- [同 tty 上多個 minicom / 競態] → 沿用 `_minicom_summary` 既有行為（取第一個命中），本 change 不改其語意。
