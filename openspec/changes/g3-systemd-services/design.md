## Context

完整設計＋審查修正：`docs/superpowers/specs/2026-07-06-g3-systemd-services-design.md`。實測：`systemctl is-system-running`＝running（system/user、PID1=systemd）——舊認知「WSL 無 systemd」過時。既有資產：`paulshaclaw/deploy/templates/{core/systemd,core/runtime,secret/bootstrap}/`＋Stage 7 測試；start.sh `stop_legacy_manager_timer` 顯示 timer 舊語意已被常駐 daemon 取代。

## Goals / Non-Goals

**Goals:** 四服務開機自起、崩潰自復；start.sh 降 dev 入口；adr-001 補寫。
**Non-Goals:** #195 主修（cgroup 只是緩解）；服務邏輯變更；system 層 unit。

## Decisions

1. **沿用 deploy 平面**（審查修正）：模板進 `paulshaclaw/deploy/templates/core/systemd/`，env 沿三分 split（runtime `~/.agents/core/runtime/__INSTANCE__-*.env`＋secret `~/.config/paulshaclaw/__INSTANCE__*.secret.env`）；per-service 必要 env 檔/鍵清單化，verify 檢存在不印值。
2. **manager 用 .service 常駐**：現行 manager_daemon 為常駐；`-manager.timer.tmpl` 標 deprecated 不部署。
3. **遷移序 cost→dream→manager→bot**：風險遞增、bot（遠端操作面）最後；每服務 cutover 觀察 ≥1 天；rollback＝disable unit→start.sh --dev（單服務粒度）。
4. **真 cold-start DoD**（審查修正）：`wsl.exe --shutdown`→重開 distro→四服務自起；linger 在 WSL 的實效以此為準；不過→Windows 啟動項 fallback 文件化後才過閘，或 owner 明示降級目標（adr 記錄）。
5. **KillMode=control-group**：worker/子進程隨 unit 收斂（#195 緩解，主修另案）。
6. **P0-2 收斂**：bot cutover 後 start.sh respawn 降級 dev-mode only（unit Restart 接手）。

## Risks / Trade-offs

- WSL linger/cold-start 語意非標準 Linux：以實測定案並寫入 adr；fallback 路徑先備。
- 操作習慣遷移：運維指令表（systemctl/journalctl 對照 start.sh 舊操作）入 adr 附錄。
- EnvironmentFile 缺失→unit 起不來：install/verify 檢查前置。
