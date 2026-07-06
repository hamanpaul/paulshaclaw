## ADDED Requirements

### Requirement: 常駐服務 systemd --user 化
部署平面 SHALL 提供四常駐（core daemon/bot、manager、dream、cost）之 `--user` service 模板：`Restart=on-failure`、`RestartSec=10`、StartLimit 防 crash-loop、`KillMode=control-group`；env 供給沿三分 split（runtime env＋secret env），每服務必要 env 檔與鍵 SHALL 清單化且可驗證存在（值不印出）；`-manager.timer` 模板 SHALL 標 deprecated 不再部署。

#### Scenario: 崩潰自復
- **WHEN** 任一服務主進程被 kill
- **THEN** systemd 於 RestartSec 後自動重啟該服務，其餘服務不受影響

#### Scenario: env 缺失前置攔截
- **WHEN** 某服務必要 env 檔缺失
- **THEN** 部署驗證（verify）exit 非零並指名該檔，unit 不進入半殘啟動

### Requirement: 開機自起（真 cold-start 驗證）
四服務 enable 後 SHALL 於 distro 冷啟動（`wsl.exe --shutdown` 後重開）自動啟動至 active；linger SHALL 冪等啟用；cold-start 不成立時 SHALL 以文件化 fallback（Windows 端啟動項）補足或經 owner 明示降級目標，否則不得宣告達成。

#### Scenario: cold-start 全起
- **WHEN** distro 經 wsl --shutdown 後重新開啟
- **THEN** 四服務皆 active，bot 可回應、dream/cost/manager 正常寫各自 ledger/status

### Requirement: 單服務 rollback
每服務 SHALL 可獨立 rollback（disable unit → start.sh dev 模式拉回），不影響其他服務。

#### Scenario: 單服務回退
- **WHEN** dream unit 被 disable 並以 dev 模式啟動
- **THEN** dream 恢復 start.sh 管理且 bot/manager/cost unit 不受影響
