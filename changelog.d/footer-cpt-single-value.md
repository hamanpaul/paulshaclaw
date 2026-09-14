---
type: change
scope: cost
---
tmux footer 的 cpt（Copilot）段收斂成單一值 `cpt N%`：只取第一個 enabled 帳號的值，不再逐帳號列 `label:value`（先前為 `cpt haman:23% arc:--`），與 cockpit 既有的 `cpt: N%` 規則一致；兩邊改共用 `_primary_account_value()`，cockpit 段因此也跟進 `stale` 時的 dim 樣式（其餘 cdx／cc／agy 段本就如此）。其餘帳號仍照常 collect、只是不呈現；sample yaml 的帳號註解同步改寫。
