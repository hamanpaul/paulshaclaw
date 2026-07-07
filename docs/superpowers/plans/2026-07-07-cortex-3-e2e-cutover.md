# paulsha-cortex Plan 3：fresh-install E2E + systemd cutover 實作計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans（本計劃為真機 E2E/cutover，多為驗證步驟而非單元測試，建議 inline 逐步執行並在每步 checkpoint）。Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在真機驗證 cortex（含 deck+monitor）可乾淨安裝、`install service` 一次帶起 manager+monitor、由舊 paulshaclaw manager 平滑 cutover 到 cortex、雙 daemon 鎖競爭與 rollback 皆如設計，證明「獨立上線可用可執行」。

**Architecture:** 依設計 spec `2026-07-07-cortex-extraction-design.md` §5（cutover 協議）、R1.4（各元件自帶 install、shell 協調）、R1.9（閉環邊界），openspec `cortex-consumer`（systemd cutover 協議、雙 daemon 鎖競爭、install 冪等）。**本計劃驗證 Plan 1b/2 的實際產出**——下列標 ⏳ 者依 1b/2 落地後的真實行為定案。

**Tech Stack:** systemd --user、pipx/venv、flock、Unix socket、bash。

## Global Constraints

- **硬前置 gate**：Plan 1b merged（cortex 含 deck+monitor、`install service` 併裝）、Plan 2 merged（主 repo pin cortex、5 包已刪）。
- 真機為 WSL2——**user systemd 可能不可用**（memory：`systemctl --user unavailable`）。每個 systemd 步驟 MUST 有 fallback 判斷：不可用時走前景/手動 supervise（G3 決策樹同型），並於報告註明「systemd unavailable，走 fallback」。
- **fresh-install E2E 必須從 source tree 外執行**（`cd /tmp`）——`cd` 進 source 會 import 到本地碼造成假通過（Plan 1 踩過的教訓）。
- cutover 前先 `git pull --ff-only`；操作 control root（`~/.agents/control`）前備份。
- 破壞性/不可逆步驟（stop/disable 既有 unit、rollback）逐步 checkpoint，先讀狀態再動。
- 報告一律 zh-tw。

---

### Task 1: fresh-install E2E（主 repo 拉 cortex+hippo）

**Files:**
- （驗證；無 code）

**Interfaces:**
- Consumes: Plan 2 merged 的主 repo main（pin cortex `<1b-pin-sha>` + hippo）
- Produces: 乾淨環境安裝證明——主 repo import 不破、psc shim 通、依賴解析含 cortex+hippo

- [ ] **Step 1: 乾淨 venv 安裝主 repo**

```bash
rm -rf /tmp/psc-e2e && python -m venv /tmp/psc-e2e
/tmp/psc-e2e/bin/pip install ~/prj_pri/paulshaclaw -q 2>&1 | tail -3
/tmp/psc-e2e/bin/pip show paulshaclaw | grep -i requires
```

Expected: 安裝成功；`Requires:` 含 `paulsha-cortex` 與 `paulsha-hippo`

- [ ] **Step 2: 從 /tmp 驗主 repo import 與 psc shim（不吃 source tree）**

```bash
cd /tmp
/tmp/psc-e2e/bin/python -c "import paulshaclaw.core.daemon, paulshaclaw.bot.listener, paulshaclaw.cockpit.app; print('main-repo import ok')"
/tmp/psc-e2e/bin/psc coordinator --help >/dev/null 2>&1; echo "psc coordinator exit=$?"
/tmp/psc-e2e/bin/psc deck compile feature-oneshot --task "e2e" >/dev/null 2>&1; echo "psc deck exit=$?"
/tmp/psc-e2e/bin/psc monitor --once >/dev/null 2>&1; echo "psc monitor exit=$?"
```

Expected: `main-repo import ok`；三個 psc shim 皆委派 cortex 成功（deck compile 載到 cortex wheel 內 cards→exit 0；monitor --once 無 config 時 exit 1 印「無 project 設定」屬預期）

- [ ] **Step 3: 記錄結果**

於報告記：安裝依賴集合、三 shim exit code、main-repo import 結果。任一 FAIL → 回 Plan 1b/2 定位（多半是 package-data 漏檔或 shim 路由）。

---

> **systemd 可用性 helper（F3.2，下列各 Task 共用）**——每個 systemd 步驟先判 `systemd_ok`，不可用時走該步驟標註的前景 fallback：
> ```bash
> systemd_ok() { systemctl --user show-environment >/dev/null 2>&1; }
> ```
> 若整機無 user systemd，systemd cutover 於報告標 **N/A**，改跑前景 daemon 驗證（Task 3/5 有 fallback 分支）；systemd 可用性亦可設為 Plan 3 硬前置（二擇一，動工時定並記於報告）。

### Task 2: 停用舊 manager/monitor（cutover 第一步——**先停舊，F3.1**）

**Interfaces:**
- Produces: 舊 `paulshaclaw-manager.*` / 遺留 `demo-manager.*` 停用；**gate：確保啟用 cortex 前無舊 unit active、無舊 daemon 持 `manager.lock`**

- [ ] **Step 1: 讀現況（先讀再動）**

```bash
systemctl --user list-units --all 2>/dev/null | grep -iE 'manager|monitor' || echo "（無既有 unit）"
cat ~/.agents/control/manager.lock 2>/dev/null || echo "（無 lock）"
```

- [ ] **Step 2: 停用舊單元 / 殺舊前景進程**

```bash
if systemd_ok; then
  for u in paulshaclaw-manager.timer paulshaclaw-manager.service demo-manager.timer demo-manager.service; do
    systemctl --user stop "$u" 2>/dev/null; systemctl --user disable "$u" 2>/dev/null && echo "disabled $u" || true
  done
else
  echo "systemd unavailable：殺前景舊 manager/monitor 進程"; pkill -f 'paulshaclaw.coordinator.manager_daemon' 2>/dev/null || true; pkill -f 'paulshaclaw.monitor' 2>/dev/null || true
fi
```

- [ ] **Step 3: 硬 gate——無舊 active/daemon 才可繼續（F3.1）**

```bash
if systemd_ok; then
  act=$(systemctl --user list-units 2>/dev/null | grep -iE 'paulshaclaw-manager|demo-manager' | grep -i active || true)
  [ -z "$act" ] || { echo "STOP：舊 unit 仍 active，不可啟用 cortex"; exit 1; }
fi
pgrep -f 'paulshaclaw.coordinator.manager_daemon' && { echo "STOP：舊 daemon 仍持鎖"; exit 1; } || echo "gate ok：無舊 daemon/unit"
```

Expected: `gate ok`（有舊 active/daemon → 中止，先解決再繼續——**不得帶著舊 unit 啟用 cortex**）

---

### Task 3: cortex install service + enable（gate 通過後才啟新）

**Interfaces:**
- Produces: cortex manager+monitor 單元落檔、冪等、enable（Task 2 gate 後）

- [ ] **Step 1: install service（render+copy+env）**

```bash
/tmp/psc-e2e/bin/cortex install service --instance cortex --repo-root ~/prj_pri/paulshaclaw
ls -la ~/.config/systemd/user/cortex-{manager.service,manager.timer,monitor.service} 2>&1
cat ~/.agents/core/runtime/cortex-manager.env
```

Expected: 三 unit 落檔；env 含 `PY=<venv python>`、`PSC_REPO_ROOT=<主 repo>`（Plan 1 F2/F3 產出）

- [ ] **Step 2: 冪等重跑**

```bash
/tmp/psc-e2e/bin/cortex install service --instance cortex --repo-root ~/prj_pri/paulshaclaw && echo "idempotent ok"
```

- [ ] **Step 3: enable+start（systemd 可用；否則前景 supervise fallback）**

```bash
if systemd_ok; then
  systemctl --user enable --now cortex-manager.timer cortex-monitor.service 2>&1
  sleep 2; systemctl --user is-active cortex-monitor.service
else
  echo "systemd N/A：前景起受控 daemon 供 Task 4/5 驗證"
  ( PSC_CONTROL_ROOT="$HOME/.agents/control" /tmp/psc-e2e/bin/python -m paulsha_cortex.coordinator.manager_daemon --specs-dir "$HOME/.agents/specs" >/tmp/mgr.out 2>&1 & echo "fg manager pid=$!" )
  ( /tmp/psc-e2e/bin/cortex monitor >/tmp/mon.out 2>&1 & echo "fg monitor pid=$!" )
fi
```

Expected: systemd 下 monitor active；fallback 下前景 daemon+monitor 起（記 PID 供後續受控競爭測試）

---

### Task 4: F1 自停 blocking gate + complete tick（F3.3/F3.6）

**Interfaces:**
- 驗 cortex issue #2 F1 自停**不得發生**；complete tick 需持久 daemon 而非僅前景 CLI

- [ ] **Step 1: F1 自停 blocking gate（issue #2）——自停即 FAIL 停 Plan**

```bash
if systemd_ok; then
  systemctl --user restart cortex-manager.service 2>&1; sleep 3
  systemctl --user is-active --quiet cortex-manager.service || { echo "FAIL：cortex-manager 自停（F1 成真）"; exit 1; }
  owner=$(sed -n 's/.*"pid":[[:space:]]*\([0-9]*\).*/\1/p' ~/.agents/control/manager.lock | head -1)
  tr '\0' ' ' < "/proc/$owner/cmdline" 2>/dev/null | grep -q 'paulsha_cortex.coordinator.manager_daemon' \
    && echo "gate ok：manager active 且 lock owner=cortex daemon(pid=$owner)" \
    || { echo "FAIL：manager.lock owner 非 cortex daemon(pid=$owner)"; exit 1; }
fi
```

Expected: `gate ok`。**FAIL（自停或 lock owner 錯）→ 停 Plan 3**：確認 issue #2 F1 為真 bug、回 cortex repo 修（`stop_legacy_manager_timer` 排除當前 instance 或移出 ExecStart 至 install 一次性 migration）、補回歸測試、重跑 Plan 1b/3。

- [ ] **Step 2: complete tick（明確命令+參數+斷言，F3.6）**

動工前 `cortex coordinator --help` 確認 tick 子命令實名；complete-tick 需 `--specs-dir`：

```bash
/tmp/psc-e2e/bin/cortex coordinator complete-tick --specs-dir "$HOME/.agents/specs"; echo "tick exit=$?"
```

Expected: `tick exit=0`（無 ready unit 空跑亦 0——證明 daemon 讀對 control/specs root）。**非 0 → 定位（specs-dir/control root 解析）**

---

### Task 5: 雙 daemon 鎖競爭 + monitor 單實例（受控觸發，F3.4）

**Interfaces:**
- 在**已知第一 daemon 持鎖/佔 socket** 的前提下起第二個，捕真實 exit（非 tail 的 exit）

- [ ] **Step 1: manager 鎖競爭**

```bash
set -o pipefail
# 前提：Task 4 gate 已確認 service（或 fallback 前景）持 manager.lock 且 owner=cortex daemon
out=$(PSC_CONTROL_ROOT="$HOME/.agents/control" timeout 10 /tmp/psc-e2e/bin/python -m paulsha_cortex.coordinator.manager_daemon --specs-dir "$HOME/.agents/specs" 2>&1); rc=$?
echo "second manager exit=$rc"; echo "$out" | tail -3
```

Expected: `rc != 0`（第二實例拿不到 flock 退出，不併行寫 control root）。**若第一 daemon 非 active（未持鎖）→ 先手動起受控 first，勿讓此手動 process 變成第一個**

- [ ] **Step 2: monitor socket 單實例（捕真狀態非 tail）**

```bash
set -o pipefail
# 前提：一個 monitor 正在 serve（service 或 fallback 前景）
timeout 5 /tmp/psc-e2e/bin/cortex monitor > /tmp/mon2.out 2>&1; rc=$?
echo "second monitor exit=$rc"; grep -i 'already listening' /tmp/mon2.out && echo "socket 拒絕 ok"
```

Expected: 第二 monitor 因 socket 佔用退出、`/tmp/mon2.out` 含 `already listening`（server.py `_prepare_socket_path` live 檢查）

---

### Task 6: monitor observe smoke（merge 生效，**temp config root 不碰真 registry，F3.5**）

**Interfaces:**
- 驗 monitor 監控集 = `project-cortex.yaml` ⊍ `project-hippo.yaml`（Plan 1b merge adapter），**於隔離 temp config root，不覆寫真機的 `~/.agents/config/paulsha/`**

- [ ] **Step 1: 於 temp config root 備兩份 registry（env 覆寫，零風險）**

```bash
E2ECFG=$(mktemp -d)/paulsha; mkdir -p "$E2ECFG"
cat > "$E2ECFG/project-cortex.yaml" <<YAML
workspaces:
  - name: prj
    path: $HOME/prj_pri
YAML
cat > "$E2ECFG/project-hippo.yaml" <<YAML
projects:
  - slug: paulshaclaw
    roots: [$HOME/prj_pri/paulshaclaw]
YAML
```

（**不寫 `~/.agents/config/paulsha/`**——那是真機 registry，覆寫會毀 curated 設定；一律走 `PSC_PROJECT_CONFIG_ROOT` 指 temp。若一定要驗真路徑，先 `cp -a ~/.agents/config/paulsha ~/.agents/config/paulsha.bak` 並於 trap 還原。）

- [ ] **Step 2: cortex monitor --once（PSC_PROJECT_CONFIG_ROOT 指 temp）驗合併集**

```bash
cd /tmp && PSC_PROJECT_CONFIG_ROOT="$E2ECFG" /tmp/psc-e2e/bin/cortex monitor --once 2>&1 | python3 -m json.tool | head -30
rm -rf "$(dirname "$E2ECFG")"   # 清 temp
```

Expected: JSON 快照含 manual workspace 掃出的 project 與 hippo roots，**同 path（`$HOME/prj_pri/paulshaclaw`）只出現一次**（realpath 去重）

---

### Task 7: rollback 演練 + 收尾

**Interfaces:**
- 驗證 §5 rollback 路徑；清理 E2E 殘留

- [ ] **Step 1: rollback 演練（不實際回退主 repo，只驗步驟可行）**

在報告記錄 rollback 步驟並乾跑驗證其命令有效：`git revert <Plan2 pin commit>` → `systemctl --user disable --now cortex-manager.timer cortex-monitor.service` → 重 enable 舊單元（若還在）。**確認 rollback 不需資料遷移**（control root 不變）。

- [ ] **Step 2: 清理 E2E venv 與測試 registry（保留真用的 config）**

```bash
rm -rf /tmp/psc-e2e
# 若 project-cortex/hippo.yaml 為 E2E 測試用臨時檔則移除；真用則保留
```

- [ ] **Step 3: DoD 總結報告**

彙整：fresh-install（依賴含 cortex+hippo、三 shim 通）、install 併裝 manager+monitor、cutover 實走 complete tick、F1 結論（自停是否成真+處置）、雙 daemon 鎖競爭、monitor merge 去重、rollback 可行、systemd 可用性。回報 orchestrator 作 #232 umbrella 收尾判斷（Plan 1/1b/2/3 全綠 → 評估 #232 close 與 cortex 轉 public track）。
