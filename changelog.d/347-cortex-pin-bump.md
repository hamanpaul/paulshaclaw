---
type: change
scope: deps
issue: 347
---
`paulsha-cortex` pin 由 7ced8df（v0.1.9，2026-08-26）升到 739cde17（v0.1.10+78，origin/main 2026-09-10）：舊 pin 讀不了現行 cortex runtime 寫出的 `coordinator-cortex/jobs.json`（`next_step_hint` 等新欄位，fail-closed），`paulshaclaw` release 路徑的 cortex local fallback manager／monitor 一起就死；升版後可正常載入現行狀態檔。operator-shell 實際 import／spawn 的 cortex 介面（`control/`、`cli.py`、`persona/contract.py`、`config/paths.py`、`deck/schema.py`＋`cards.yaml`、`coordinator/{workflow,manager_daemon,registry}.py`、`monitor/`、`trust_root/selfcheck.py`）自 7ced8df 以來零變動；唯一相關的行為變動是 manager status 多輸出 `next_step_hint` 鍵，cockpit 早已容錯讀取。
