---
type: change
scope: cli
issue: 357
---
`psc` 不帶參數時不再印 usage 並以 exit 2 結束，改為等同 `paulshaclaw`（`up`）啟動 operator shell，讓 CLI 短名可直接啟動；回傳值逐字透傳 launcher。dispatcher 語意不變：`psc coordinator|deck|monitor …` 仍 shim 到 cortex CLI、`psc memory` 仍印 hippo tombstone、未知子命令仍印 usage 並 exit 2（usage 補一行說明無參數＝啟動）。`down`／`status`／`--no-cockpit` 不併入 `psc`，仍只屬 `paulshaclaw`。README §A 的安裝確認步驟改用 `paulshaclaw --version`，不再依賴「psc exit 2 屬正常」的語意。
