---
dispatch: hold
slice_id: g3-systemd-services
plan: docs/superpowers/plans/2026-07-06-g3-systemd-services.md
depends_on: []
---

# G3 — 常駐服務全 systemd --user 化 + adr-001 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#126（附帶緩解 #195）
> 父件：`2026-07-06-p3-standup-gates-umbrella-design.md`。選路裁決（owner，2026-07-06）：**全 systemd --user**。
> 實測依據：目標 WSL distro `systemctl is-system-running`＝`running`（system 與 user 兩層、PID1=systemd）——舊認知「WSL 無 systemd」已過時，寫入 adr-001。

## 1. 背景與問題

四個常駐（bot／manager_daemon／dream loop／cost loop）全掛在 start.sh 前景 supervisor：無開機自起、start.sh 死＝全滅、崩潰恢復靠手動。**（review 修正）**套件內 `paulshaclaw/deploy/templates/` **已有** Stage 7 三分部署的 systemd/env/secret 模板家族（`core/systemd/__INSTANCE__{,-telegram,-manager}.service.tmpl`＋`-manager.timer.tmpl`、`core/runtime/*.env.tmpl`、`secret/bootstrap/*.secret.env.tmpl`）與對應測試——本件是**延伸既有 deploy 平面**（補 dream/cost 模板＋接線＋cutover），不是從零寫；repo 根層 `deploy/` 無檔為先前探索誤判。

## 2. 目標與非目標

**目標**：四服務 systemd --user 化（開機自起、崩潰自復）；start.sh 降級為 dev 入口；adr-001 補寫。
**非目標**：#195 主修（cgroup 收斂只是附帶緩解）；服務邏輯變更（loop 內容原樣搬遷）；system 層 unit（一律 `--user`）。

## 3. 設計

### 3.1 服務抽取
- start.sh 內四個 loop 各抽成獨立腳本：`scripts/service-bot.sh`／`service-manager.sh`／`service-dream.sh`／`service-cost.sh`（內容＝現行對應函式體，含 idle-gate/interval 語意原樣）。
- start.sh 改薄：`--dev` 直跑腳本（現行為預設，行為不變）；無參數印出 systemctl 提示。過渡期兩模式並存，cutover 完成後 dev 模式保留。

### 3.2 unit 檔（review 修正：沿用既有 deploy planner/templates，非新開 `deploy/systemd/`）
- 模板落點＝`paulshaclaw/deploy/templates/core/systemd/`：既有 `__INSTANCE__.service.tmpl`（core daemon）、`-telegram.service.tmpl`（bot）沿用調整；**新增** `-dream.service.tmpl`、`-cost.service.tmpl`。manager 裁決：現行為**常駐** `manager_daemon` → 用 `.service`（Type=simple 常駐）；既有 `-manager.timer.tmpl`（oneshot tick 舊語意）標 deprecated、不部署（start.sh 已有 `stop_legacy_manager_timer` 清理先例）。
- unit 參數：`Restart=on-failure`、`RestartSec=10`、`StartLimitIntervalSec=300`/`StartLimitBurst=5`（防 crash-loop 風暴）、`KillMode=control-group`（子進程一併收斂——#195 緩解）。
- env 模型沿**既有三分 split**（非單一 env 檔）：runtime env（`~/.agents/core/runtime/__INSTANCE__-*.env` 家族）＋ secret（`~/.config/paulshaclaw/__INSTANCE__*.secret.env`）；**每服務逐一列舉必要 env 檔與必要鍵**（plan 內落實成 checklist；`--verify` 檢存在性不印值）。unit 內零硬編碼個人路徑（`%h`＋EnvironmentFile）。
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
- cutover 驗收（per service）：`systemctl --user is-active`＝active；kill 主進程 → RestartSec 後自復；`loginctl show-user "$USER" | grep Linger=yes`；該服務必要 env 檔/鍵存在性檢查通過。
- e2e（DoD，review 修正——用**真 cold-start**非 shell 重登）：四服務 enable 後，Windows 端 `wsl.exe --shutdown` → 重開 distro → 四服務全部自起 active；bot 回應 Telegram、dream/cost/manager 正常寫各自 ledger/status。cold-start 不過 → fallback（Windows 啟動項拉起 distro）落地並文件化後**才算過閘**，或經 owner 明示把 DoD 降級為 session 級服務管理（adr-001 記錄）。

## 5. 風險

- WSL 重啟語意（Windows 端 shutdown distro）≠ Linux reboot：linger 在 WSL 下的行為以實測為準，adr-001 記錄實測結果；不符預期時 fallback＝Windows 端啟動項拉 `wsl -d <distro>`（文件化，不擋本件）。
- tmux 操作習慣改變：cockpit／tmux pane 改 tail journal；運維指令表入 adr-001 附錄。
- EnvironmentFile 缺失 → unit 啟動失敗：install --verify 檢查該檔存在與必要鍵（值不印出）。
