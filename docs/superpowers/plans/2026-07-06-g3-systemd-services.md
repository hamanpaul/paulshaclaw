# G3 常駐服務全 systemd --user 化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> **實作者：gpt5.3-codex**（Task 1–3 純 code/模板可 headless；**Task 4 cutover 為 on-host ops，須 owner 在場逐服務執行**）。分支 `feature/126-g3-systemd-services`，worktree。
> 依據：`openspec/changes/g3-systemd-services/`＋`docs/superpowers/specs/2026-07-06-g3-systemd-services-design.md`（審查修正：沿用 deploy 平面、真 cold-start）。

**Goal:** 四常駐 systemd --user 化（開機自起/崩潰自復/單服務 rollback）；start.sh 降 dev 入口；adr-001 補寫。

**Architecture:** start.sh 四 loop 抽 `scripts/service-*.sh` → deploy templates 延伸（沿 `__INSTANCE__` 家族＋三分 env split）→ 一次一服務 cutover（cost→dream→manager→bot）→ 真 cold-start 驗收。

**錨點**：`scripts/start.sh:158`（start_cost_refresh_loop）`:191`（start_dream_loop）`:304`（start_manager_loop）`:345`（start_manager_service）`:232`（stop_legacy_manager_timer 先例）；`paulshaclaw/deploy/templates/core/systemd/__INSTANCE__{,-telegram,-manager}.service.tmpl`＋`-manager.timer.tmpl`（deprecated 對象）；`core/runtime/__INSTANCE__-*.env.tmpl`、`secret/bootstrap/__INSTANCE__*.secret.env.tmpl`；deploy planner 測試（tests/ 中 stage7 相關）。

---

### Task 1: 服務腳本抽取（start.sh 減脂）

**Files:** Create `scripts/service-cost.sh`／`service-dream.sh`／`service-manager.sh`／`service-bot.sh`；Modify `scripts/start.sh`；Test `tests/test_service_scripts.py`（新）

- [ ] **Step 1: 失敗測試**（沿 test_start_sh 讀檔斷言模式，避開 SIGKILL——#195 坑）

```python
def test_service_scripts_exist_and_sane():
    for name in ("cost", "dream", "manager", "bot"):
        p = REPO / "scripts" / f"service-{name}.sh"
        assert p.is_file() and os.access(p, os.X_OK)
        head = p.read_text().splitlines()[0]
        assert head.startswith("#!")

def test_start_sh_dev_mode_delegates():
    text = (REPO / "scripts" / "start.sh").read_text()
    for name in ("cost", "dream", "manager", "bot"):
        assert f"service-{name}.sh" in text   # start.sh 改呼叫腳本而非內嵌函式體
```

- [ ] **Step 2: RED → Step 3:** 四函式體逐一搬進腳本（**逐字搬遷，不改邏輯**——含 dream 的 `--require-idle`/instruction-root env、manager 的 lock 語意）；start.sh 對應函式改為呼叫腳本；GREEN＋既有 start.sh 測試零回歸。
- [ ] **Step 4: Commit** `refactor(start): 四常駐 loop 抽成 scripts/service-*.sh（行為零變更）`

### Task 2: deploy 模板延伸

**Files:** Create `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-dream.service.tmpl`、`__INSTANCE__-cost.service.tmpl`；Modify `-manager` 相關（.service 常駐化、.timer 標 deprecated）、planner 對應；Test 既有 stage7 deploy 測試檔加案例

- [ ] **Step 1: 失敗測試**：渲染四 unit → 內容含 `Restart=on-failure`/`RestartSec=10`/`StartLimitIntervalSec=300`/`StartLimitBurst=5`/`KillMode=control-group`、`ExecStart` 指向 service 腳本、`EnvironmentFile` 指向 runtime env＋secret env（`%h` 路徑、零 `/home/` 字面）；timer 模板不再出現在部署清單。
- [ ] **Step 2: RED → Step 3:** 模板新增/調整＋planner 清單更新＋per-service 必要 env 鍵宣告（dream 需 memory root/instruction roots；bot 需 telegram secret；manager 需 control root；cost 需 usage 來源——鍵名以現行 env 檔為準逐一列舉）；`systemd-analyze --user verify` 於 install --verify 內執行（CI 無 user bus 則標記 on-host only）。
- [ ] **Step 4: GREEN → Commit** `feat(deploy): dream/cost unit 模板＋manager 常駐 service＋timer deprecated`

### Task 3: install 與 verify

**Files:** Modify deploy install 路徑（unit 複製到 `~/.config/systemd/user/`＋`daemon-reload`）＋`loginctl enable-linger` 冪等；Test 假 $HOME 測試

- [ ] **Step 1: RED**：假 $HOME install 兩次冪等；env 檔缺失 → verify 非零指名。
- [ ] **Step 2: 實作＋GREEN → Commit** `feat(deploy): systemd unit 安裝冪等＋linger＋env 存在性 verify`

### Task 4: cutover（**on-host ops，owner 在場；一次一服務**）

- [ ] 4.1 cost：stop start.sh 側 → `systemctl --user enable --now <inst>-cost` → 驗證 cost cache 更新 → 觀察 ≥1 天
- [ ] 4.2 dream：同上＋驗 idle-gate/lock 跨遷移不變（dream ledger 正常滾動、無雙實例）
- [ ] 4.3 manager：驗 manager.lock 單實例互斥（start.sh 側殘留 supervisor 須先停）
- [ ] 4.4 bot（最後）：cutover 後把 P0-2 respawn 降級 dev-mode only（start.sh 註記）
- [ ] 4.5 **真 cold-start DoD**：Windows 端 `wsl.exe --shutdown` → 重開 distro → `systemctl --user is-active` 四服務全 active、bot 回應、三 loop 寫 ledger/status；不過 → Windows 啟動項 fallback 文件化後才勾此項

### Task 5: adr-001 與收尾

- [ ] 5.1 Create `docs/adr/adr-001-always-on-deployment.md`：實測依據（PID1=systemd/user running）、選路裁決與理由、rollback 程序、systemctl/journalctl↔舊 start.sh 操作對照表
- [ ] 5.2 全套件綠；PR body `Closes #126`

---

**Self-review**：spec 三 requirement（systemd 化+env 清單/cold-start/rollback）↔ Task 2/4/3+4.5；timer deprecated、#195 緩解、P0-2 收斂皆入任務；無 TBD——Task 2 env 鍵「以現行 env 檔為準逐一列舉」是對既有檔的枚舉指令，非佔位。
