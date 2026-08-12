---
type: fix
---
`paulsha-cortex` pin 升到正式 release **v0.1.8** 的 SHA（`dc8a968`），取代 v0.1.4（`b868760`）。v0.1.8 收進 repo 歸屬鏈全通（cortex#465 workflow-lane manifest、cortex#469 slice-lane 顯式宣告）等四個 fix，本機 pipx 部署已同步升至 v0.1.8 並重啟 manager/monitor units，pin 與部署版本一致。
- `paulsha-hippo` 本輪仍**不動**（成對升級原則下先驗證 `persona/contract.py` 的 `PHASES` 於 v0.1.4→v0.1.8 零變更，`tests/test_cortex_alignment.py` 不受單升影響）。
