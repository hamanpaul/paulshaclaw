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

### Task 2: cortex install service（一次裝 manager + monitor）

**Interfaces:**
- Produces: `<instance>-manager.{service,timer}` + `<instance>-monitor.service` 落檔並（systemd 可用時）enable

- [ ] **Step 1: 偵測 user systemd 可用性**

```bash
if systemctl --user show-environment >/dev/null 2>&1; then echo "systemd: available"; else echo "systemd: UNAVAILABLE (走 fallback)"; fi
```

- [ ] **Step 2: 跑 install service（repo-root 指主 repo）**

```bash
/tmp/psc-e2e/bin/cortex install service --instance cortex --repo-root ~/prj_pri/paulshaclaw
ls -la ~/.config/systemd/user/cortex-manager.service ~/.config/systemd/user/cortex-manager.timer ~/.config/systemd/user/cortex-monitor.service 2>&1
cat ~/.agents/core/runtime/cortex-manager.env
```

Expected: 三個 unit 落檔；env file 含 `PY=<venv python>`、`PSC_REPO_ROOT=<主 repo>`（Plan 1 F2/F3 修正產出）

- [ ] **Step 3: 冪等重跑**

```bash
/tmp/psc-e2e/bin/cortex install service --instance cortex --repo-root ~/prj_pri/paulshaclaw && echo "idempotent ok"
```

Expected: 第二次成功、狀態不變（openspec install 冪等情境）

- [ ] **Step 4: ⏳ systemd 可用時驗 enable 狀態**

```bash
systemctl --user is-enabled cortex-manager.timer cortex-monitor.service 2>&1
```

Expected: `enabled`（systemd 不可用則跳過、報告註明 fallback）

---

### Task 3: cutover 協議（舊 manager → cortex）

**Interfaces:**
- Consumes: 既有 paulshaclaw manager 單元（`paulshaclaw-manager.timer` 等，若機上有）
- Produces: 舊單元停用、cortex 單元接管、complete tick 實走

- [ ] **Step 1: 讀取現況（先讀再動）**

```bash
systemctl --user list-units --all 2>/dev/null | grep -iE 'manager|monitor' || echo "（無既有 unit）"
cat ~/.agents/control/manager.lock 2>/dev/null || echo "（無 lock）"
```

記錄機上是否有舊 `paulshaclaw-manager.*` 或 Plan 1 遺留的 `demo-manager.*`（見 cortex 討論殘留）。

- [ ] **Step 2: 停用舊單元（§5 cutover 協議）**

```bash
for unit in paulshaclaw-manager.timer paulshaclaw-manager.service demo-manager.timer demo-manager.service; do
  systemctl --user stop "$unit" 2>/dev/null && systemctl --user disable "$unit" 2>/dev/null && echo "stopped+disabled $unit" || true
done
```

- [ ] **Step 3: enable + start cortex 單元**

```bash
systemctl --user enable --now cortex-manager.timer cortex-monitor.service 2>&1
sleep 2
systemctl --user is-active cortex-monitor.service; systemctl --user status cortex-manager.timer --no-pager 2>&1 | head -5
```

Expected: monitor active；manager timer active（systemd 不可用 → 走 `cortex` 前景 supervise，報告註明）

- [ ] **Step 4: complete tick 實走**

```bash
/tmp/psc-e2e/bin/cortex coordinator tick 2>&1 | tail -10   # 子命令名以 cortex coordinator CLI 為準
```

Expected: manager 掃 specs、完成一次 tick 無錯（無 ready unit 時空跑亦算通過——證明 daemon 起得來、讀對 control/specs root）

---

### Task 4: ⏳ F1 自停 + 雙 daemon 鎖競爭 + monitor 單實例

**Interfaces:**
- 驗證 cortex issue #2 的 F1（`stop_legacy_manager_timer` 自停）在真 systemd 下的實際行為，與 §4.6 單寫者不變量

- [ ] **Step 1: ⏳ F1 自停實測（issue #2）**

cortex-manager.service ExecStart 跑 `service-manager.sh` → `stop_legacy_manager_timer` 停 `cortex-manager.*`。**觀察 manager 是否被自己停掉**：

```bash
systemctl --user restart cortex-manager.service 2>&1
sleep 3
systemctl --user is-active cortex-manager.service; pgrep -af 'paulsha_cortex.coordinator.manager_daemon' | head -1 || echo "（無 daemon 進程——F1 可能咬到）"
```

Expected（依實際）：daemon 起得來且未被自停。**若 daemon 被自停**→ 確認 issue #2 的 F1 為真 bug，於此修正（`stop_legacy_manager_timer` 排除當前 instance，或移出 ExecStart 到 install 一次性 migration），補回歸測試後回 cortex repo 開修正 PR。

- [ ] **Step 2: 雙 daemon 鎖競爭（§4.6）**

```bash
# daemon 已由 service 持 manager.lock；手動再起一個應拿不到鎖而退出
PSC_CONTROL_ROOT="$HOME/.agents/control" /tmp/psc-e2e/bin/python -m paulsha_cortex.coordinator.manager_daemon --specs-dir "$HOME/.agents/specs" 2>&1 | tail -3; echo "second exit=$?"
```

Expected: 第二實例因 `manager.lock` flock 拿不到鎖而退出，不併行寫 control root

- [ ] **Step 3: monitor 單實例（socket 佔用）**

```bash
/tmp/psc-e2e/bin/cortex monitor 2>&1 | tail -3 &   # 第二個 monitor serve
sleep 1; echo "（預期印 'live monitor already listening'）"; kill %1 2>/dev/null || true
```

Expected: 第二個 monitor 因 socket 已被佔用而拒絕啟動（server.py `_prepare_socket_path` 的 live 檢查）

---

### Task 5: ⏳ monitor observe smoke（merge 生效）

**Interfaces:**
- 驗 monitor 監控集 = `project-cortex.yaml` ⊍ `project-hippo.yaml`（Plan 1b merge adapter）在真機生效

- [ ] **Step 1: 備 manual + hippo 兩份 registry**

```bash
mkdir -p ~/.agents/config/paulsha
cat > ~/.agents/config/paulsha/project-cortex.yaml <<YAML
workspaces:
  - name: prj
    path: $HOME/prj_pri
YAML
# project-hippo.yaml 若 hippo#14 未落地則手寫最小版驗 merge
cat > ~/.agents/config/paulsha/project-hippo.yaml <<YAML
projects:
  - slug: paulshaclaw
    roots: [$HOME/prj_pri/paulshaclaw]
YAML
```

- [ ] **Step 2: cortex monitor --once 驗合併集**

```bash
cd /tmp && /tmp/psc-e2e/bin/cortex monitor --once 2>&1 | python3 -m json.tool | head -30
```

Expected: JSON 快照含 manual workspace 掃出的 project 與 hippo roots，**同 path 只出現一次**（realpath 去重）；無 config 時的 FAIL 路徑不觸發

---

### Task 6: rollback 演練 + 收尾

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
