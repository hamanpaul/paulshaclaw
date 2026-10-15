## Why

v0.2.10 的告警優先與帳號明細違反 operator 已確認的單值呈現；次帳號 unknown 取代主帳號用量並擠壓 cockpit。

## What Changes

- 恢復設定中第一個 enabled 帳號的單值 cpt 摘要，不顯示帳號名或明細。
- 次帳號保留收集與 cache，但其狀態不得取代主帳號或污染摘要標記。

## Impact

Stage 8 formatter、cockpit banner 與對應測試/說明；不新增設定或變更 live 帳號配置。
