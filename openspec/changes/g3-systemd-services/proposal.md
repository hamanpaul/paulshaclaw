## Why

四常駐（bot/manager/dream/cost）全掛 start.sh 前景 supervisor：無開機自起、start.sh 死＝全滅（#126）。systemd 實測可用（PID1=systemd、user 層 running），owner 裁決全 systemd --user 化；套件內 deploy 平面已有 systemd/env/secret 模板家族，本件為延伸非新造。

## What Changes

- start.sh 四 loop 抽成 `scripts/service-{bot,manager,dream,cost}.sh`；start.sh 降為 `--dev` 入口。
- deploy templates 延伸：沿用 `__INSTANCE__.service.tmpl`/`-telegram.service.tmpl`，**新增** `-dream.service.tmpl`/`-cost.service.tmpl`；`-manager.timer.tmpl` 標 deprecated（現行為常駐 daemon 用 .service）。
- unit 參數：Restart=on-failure、RestartSec=10、StartLimit 防風暴、KillMode=control-group（#195 緩解）；env 沿三分 split（runtime env＋secret env），per-service 必要鍵清單化。
- `loginctl enable-linger` 冪等安裝；遷移序 cost→dream→manager→bot（一次一服務、可單服務 rollback）。
- DoD 用真 cold-start：`wsl.exe --shutdown` 後重開 distro 四服務自起；不過則 fallback 文件化才過閘。
- 補寫 `adr-001-always-on-deployment`（實測依據、選路、rollback、運維指令表）。
- G3 落地後 P0-2 的 start.sh bot respawn 降級為 dev-mode only。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `stage7`: 部署平面新增 dream/cost 服務模板與常駐 manager service 裁決；服務生命週期治理（自起/自復/rollback）要求。

## Impact

- 受影響碼：`scripts/start.sh`、`scripts/service-*.sh`（新）、`paulshaclaw/deploy/templates/core/systemd/`、deploy planner/測試、`docs/adr/`。
- 運維：tmux 觀察面改 journalctl/log tail；cutover 期間服務逐一切換。
- 依據：`docs/superpowers/specs/2026-07-06-g3-systemd-services-design.md`（含 codex 審查修正：沿用 deploy 平面、真 cold-start 驗證）。
