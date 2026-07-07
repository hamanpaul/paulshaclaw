# ADR-001：always-on 服務部署模型——全 systemd --user

- 狀態：Accepted（2026-07-07）
- 對應：#126（G3）、#195（附帶緩解）、傘狀 `docs/superpowers/specs/2026-07-06-p3-standup-gates-umbrella-design.md`

## 背景

四個常駐（bot listener／manager_daemon／dream loop／cost refresh loop）原全掛在 `scripts/start.sh` 前景 supervisor：無開機自起、start.sh 死＝全滅、崩潰恢復靠手動。G3 傘狀裁決要求「先驗證 systemd 可用性再選路」。

## 實測依據

| 檢查 | 結果 | 主機 |
|---|---|---|
| `systemctl is-system-running` | `running`（system 層） | 開發／目標 WSL distro（2026-07-06） |
| `systemctl --user is-system-running` | `running`（user 層） | 同上＋fresh-install 驗證機（2026-07-06 實測 `running` + `Linger=yes`） |
| PID1 | systemd | 同上 |

舊認知「WSL 無 systemd」已過時（WSL2 systemd=true 世代）。

## 選路裁決

**全 systemd `--user`**（owner 裁決，2026-07-06）。放棄之替代案：

- *hybrid（部分 systemd＋start.sh 殘留）*：雙 supervisor 責任邊界模糊，崩潰恢復語意不一致。
- *start.sh supervisor 加固（respawn/backoff/健康檔）*：已由 P0-2（#205）做為過渡，但無開機自起、失敗域仍集中單一前景 process；僅在 systemd 不可用主機作為 fallback 保留。

實作：四 loop 抽成 `scripts/service-{bot,cost,dream,manager}.sh`（行為零變更），deploy 平面模板家族補 `-dream`/`-cost` unit、manager 改常駐 service（timer deprecated）；`start.sh` 降級為 dev 入口（`--dev` 直跑，內部委派同一批 service 腳本）。

## Rollback

1. `systemctl --user disable --now <instance>-{bot,dream,cost,manager}.service`
2. 以 `scripts/start.sh` 前景啟動（P0-2 respawn 護欄仍在，dev-mode）
3. unit 檔案位於 `~/.config/systemd/user/`，`python -m paulshaclaw.deploy uninstall` 可逆移除

## 觀察面（取代 tmux 前景輸出）

- `journalctl --user -u <instance>-dream -f`（等）取代 start.sh pane tail
- 服務 log 仍落 `~/.agents/log/*.log`（雙軌），cockpit/monitor 讀檔面不變

## 拆分注記（#125 Phase 1）

`-dream` unit 為 **will-migrate-to-hippo** 標的：拆分後 dream 常駐（unit 產生與生命週期）移交 `paulsha-hippo` installer（`hippo install service`），本 repo deploy planner 屆時移除 dream 模板；cutover 程序見 `docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md` §5.5/§6。
