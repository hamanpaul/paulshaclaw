---
dispatch: hold
slice_id: g3-systemd-services
plan: null
depends_on: []
---

# G3 — 常駐服務全 systemd --user 化 + adr-001 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#126（附帶緩解 #195）
> 父件：`2026-07-06-p3-standup-gates-umbrella-design.md`。選路裁決（owner，2026-07-06）：**全 systemd --user**。
> 實測依據：目標 WSL distro `systemctl is-system-running`＝`running`（system 與 user 兩層、PID1=systemd）——舊認知「WSL 無 systemd」已過時，寫入 adr-001。

## 1. 背景與問題

四個常駐（bot／manager_daemon／dream loop／cost loop）全掛在 start.sh 前景 supervisor：無開機自起、start.sh 死＝全滅、崩潰恢復靠手動。`deploy/templates/` 下實際**無** unit 檔（早前文件引用的 templates 不存在，本件從零寫）。

## 2. 目標與非目標

**目標**：四服務 systemd --user 化（開機自起、崩潰自復）；start.sh 降級為 dev 入口；adr-001 補寫。
**非目標**：#195 主修（cgroup 收斂只是附帶緩解）；服務邏輯變更（loop 內容原樣搬遷）；system 層 unit（一律 `--user`）。

## 3. 設計

### 3.1 服務抽取
- start.sh 內四個 loop 各抽成獨立腳本：`scripts/service-bot.sh`／`service-manager.sh`／`service-dream.sh`／`service-cost.sh`（內容＝現行對應函式體，含 idle-gate/interval 語意原樣）。
- start.sh 改薄：`--dev` 直跑腳本（現行為預設，行為不變）；無參數印出 systemctl 提示。過渡期兩模式並存，cutover 完成後 dev 模式保留。

### 3.2 unit 檔（repo 版控 `deploy/systemd/`，install 複製到 `~/.config/systemd/user/`）
- 四個 `.service`：`Type=simple`、`ExecStart=<abs path via ${PSC_REPO_ROOT}>/scripts/service-<name>.sh`、`Restart=on-failure`、`RestartSec=10`、`StartLimitIntervalSec=300`/`StartLimitBurst=5`（防 crash-loop 風暴）、`KillMode=control-group`（子進程一併收斂——#195 緩解）。
- secret／env：`EnvironmentFile=%h/.config/paulshaclaw/env`（path-split 契約：secret 空間）；unit 檔內零硬編碼個人路徑（`%h` + EnvironmentFile 提供 `PSC_REPO_ROOT` 等）。
- `loginctl enable-linger "$USER"` → 開機自起（install 步驟，冪等）。

### 3.3 遷移序（一次一服務，bot 最後）
1. cost（最低風險）→ 2. dream（驗 idle-gate 與 lock 語意跨遷移不變）→ 3. manager（驗 manager.lock 單實例互斥在 systemd 下成立）→ 4. bot（遠端操作面，最後）。
- 每服務 cutover：stop start.sh 側 → `systemctl --user enable --now` → 驗證功能 → 觀察 ≥1 天再下一個。
- rollback：`systemctl --user disable --now <unit>` → start.sh --dev 拉回（單服務粒度）。

### 3.4 adr-001-always-on-deployment
- 記錄：實測依據（PID1=systemd、user 層 running）、選路（全 systemd vs hybrid vs start.sh 加固——owner 裁決與理由）、rollback 程序、與 tmux 觀察面的關係（journalctl -f／log tail pane 取代前景輸出）。

### 3.5 與 P0-2 的交互
- P0-2 的 start.sh bot respawn 先行不衝突；G3 bot cutover 後該 respawn 降級為 dev-mode only（unit `Restart=` 接手），plan 內含此收斂步驟。

## 4. 測試

- unit 檔靜態驗證：`systemd-analyze --user verify deploy/systemd/*.service`（CI 可跑則入 CI，不可跑則入 install --verify）。
- 腳本抽取回歸：既有 start.sh 相關測試改指向 service 腳本（沿 test_start_sh* 模式，避開 SIGKILL 情境）。
- cutover 驗收（per service）：`systemctl --user is-active`＝active；kill 主進程 → RestartSec 後自復；`loginctl show-user "$USER" | grep Linger=yes`。
- e2e（DoD）：四服務 enable 後重登 shell（模擬開機）全部 active；bot 回應 Telegram、dream/cost/manager tick 正常寫各自 ledger/status。

## 5. 風險

- WSL 重啟語意（Windows 端 shutdown distro）≠ Linux reboot：linger 在 WSL 下的行為以實測為準，adr-001 記錄實測結果；不符預期時 fallback＝Windows 端啟動項拉 `wsl -d <distro>`（文件化，不擋本件）。
- tmux 操作習慣改變：cockpit／tmux pane 改 tail journal；運維指令表入 adr-001 附錄。
- EnvironmentFile 缺失 → unit 啟動失敗：install --verify 檢查該檔存在與必要鍵（值不印出）。
