# paulsha-cortex Plan 2：主 repo 遷移刀（刪 5 包 + pin cortex）實作計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 主 repo `paulshaclaw` 刪除已遷入 cortex 的 5 包（persona/coordinator/control/deck/monitor），改以 SHA pin 依賴 `paulsha-cortex`，重接消費者 import 與 `psc` shim，補三個對齊測試，收斂主 repo 為純 operator shell。

**Architecture:** 依設計 spec `2026-07-07-cortex-extraction-design.md` §R1（R1.5 契約、R1.9 閉環邊界）與 §5（cutover 協議），openspec `cortex-extraction` tasks §2/§3 + specs（`cortex-consumer`、`psc-cli-entry`）。這是 **BREAKING**：刪包 + pin 必須同一 PR atomic。

**Tech Stack:** Python 3.10+、pytest、gh CLI、pip（git+SHA pin）。

## Global Constraints

- **硬前置 gate**：Plan 1b 已 merge 且產出 cortex main 的新 pin SHA（下稱 `<1b-pin-sha>`，取代 Plan 1 的 `2e67100`）。本計劃所有 `<1b-pin-sha>` 佔位符於動工時填實值。
- 工作 repo：`~/prj_pri/paulshaclaw`，於 worktree `.worktrees/232-cortex-extraction`（分支 `feature/232-cortex-extraction`，已含 spec/openspec/Plan 1b/2/3 文件）。
- 主 repo runtime 程式碼 **MUST NOT** import `paulsha_cortex` 內部模組——僅允許 `paulsha_cortex.control.client`（bot/cockpit/core）與 `psc` shim 對 cortex CLI 入口（coordinator/deck/monitor）的 lazy import（openspec `cortex-consumer`「允許 import 面限定」）。
- 測試面例外：主 repo 測試 MAY import `paulsha_hippo.lib.lifecycle.schema`，僅供 PHASES 對齊測試。
- monitor 的 live-query 消費（cockpit 若接）走 Unix socket，MUST NOT python import `paulsha_cortex.monitor`。
- 所有文件與 commit zh-tw；conventional commit；PR 掛 `policy-exempt:issue-link` + `skip-changelog`；相對 import（`from ..control`）與絕對 import 都要改。
- R-18 docs 對齊：本刀改 `code_paths`，README/CLAUDE.md 同 PR 更新。

---

### Task 1: pin cortex 依賴

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `paulsha-cortex @ git+…@<1b-pin-sha>` 依賴；`paulsha-hippo` pin 保留（PHASES 對齊測試需同裝）

- [ ] **Step 1: 寫失敗測試（依賴宣告存在性）**

```python
# tests/test_cortex_consumer_pin.py
import tomllib
from pathlib import Path


def test_pyproject_pins_cortex_by_sha():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    deps = " ".join(data["project"]["dependencies"])
    assert "paulsha-cortex @ git+https://github.com/hamanpaul/paulsha-cortex@" in deps
    # 40 字元 SHA、非 branch/tag
    import re
    assert re.search(r"paulsha-cortex @ git\+https://github.com/hamanpaul/paulsha-cortex@[0-9a-f]{40}", deps)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_cortex_consumer_pin.py -v`
Expected: FAIL（尚無 cortex 依賴）

- [ ] **Step 3: pyproject 加 pin**

`pyproject.toml` `dependencies` 追加（`<1b-pin-sha>` 填實值）：

```toml
dependencies = [
    "paulsha-hippo @ git+https://github.com/hamanpaul/paulsha-hippo@30ebbbd598ec1e43c8b663c12f4ff1cffde3fc79",
    "paulsha-cortex @ git+https://github.com/hamanpaul/paulsha-cortex@<1b-pin-sha>",
]
```

- [ ] **Step 4: 乾淨環境可安裝**

Run: `python -m pip install -e . -q && python -m pytest tests/test_cortex_consumer_pin.py -v`
Expected: 安裝成功、PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_cortex_consumer_pin.py
git commit -m "feat: pin paulsha-cortex 依賴（<1b-pin-sha>）"
```

---

### Task 2: control.client 消費者改線（含相對 import）

**Files:**
- Modify: `paulshaclaw/core/daemon.py:14`、`paulshaclaw/bot/listener.py:17`、`paulshaclaw/cockpit/app.py:7`

**Interfaces:**
- Consumes: `paulsha_cortex.control.client`（cortex 已提供）
- Produces: 三個消費者改指 cortex；cockpit 的相對 import `from ..control` 一併改為絕對

- [ ] **Step 1: 改三處 import**

```bash
cd ~/prj_pri/paulshaclaw
sed -i 's/from paulshaclaw.control import client/from paulsha_cortex.control import client/' paulshaclaw/core/daemon.py paulshaclaw/bot/listener.py
sed -i 's/from paulshaclaw.control.client import ControlPlaneCoordinator/from paulsha_cortex.control.client import ControlPlaneCoordinator/' paulshaclaw/bot/listener.py
sed -i 's/from \.\.control import client as control_client/from paulsha_cortex.control import client as control_client/' paulshaclaw/cockpit/app.py
grep -rn 'paulshaclaw.control\|from ..control\|from .control' paulshaclaw/core paulshaclaw/bot paulshaclaw/cockpit --include='*.py' | grep -v __pycache__ || echo CLEAN
```

Expected: `CLEAN`（三處皆改；實際 import 行文字以動工時 grep 為準，勿漏相對 import 形式）

- [ ] **Step 2: 冒煙 import**

Run: `python -c "import paulshaclaw.core.daemon, paulshaclaw.bot.listener, paulshaclaw.cockpit.app; print('ok')"`
Expected: `ok`（cortex 已裝，import 解析成功）

- [ ] **Step 3: Commit**

```bash
git add paulshaclaw/core/daemon.py paulshaclaw/bot/listener.py paulshaclaw/cockpit/app.py
git commit -m "refactor: control.client 消費者改指 paulsha_cortex（含 cockpit 相對 import）"
```

---

### Task 3: psc CLI shim（coordinator/deck/monitor → cortex）

**Files:**
- Modify: `paulshaclaw/cli.py`
- Test: `tests/test_psc_cli_shim.py`（新增，對齊 openspec `psc-cli-entry`）

**Interfaces:**
- Produces: `psc coordinator|deck|monitor` thin shim lazy import cortex CLI；cortex 未安裝時 tombstone + exit 2；移除 `paulshaclaw.{coordinator,deck}` 路由

- [ ] **Step 1: 寫失敗測試（對齊 psc-cli-entry 情境）**

```python
# tests/test_psc_cli_shim.py
import subprocess, sys
from paulshaclaw.cli import main


def test_deck_routes_to_cortex(monkeypatch):
    seen = {}
    import paulsha_cortex.cli
    monkeypatch.setattr(paulsha_cortex.cli, "main", lambda argv=None: seen.setdefault("a", list(argv or [])) or 0)
    assert main(["deck", "verify"]) == 0
    assert seen["a"] == ["deck", "verify"]


def test_monitor_routes_to_cortex(monkeypatch):
    seen = {}
    import paulsha_cortex.cli
    monkeypatch.setattr(paulsha_cortex.cli, "main", lambda argv=None: seen.setdefault("a", list(argv or [])) or 0)
    assert main(["monitor", "--once"]) == 0
    assert seen["a"] == ["monitor", "--once"]


def test_no_paulshaclaw_deck_route():
    # 確保不再 import 主 repo deck（Plan 2 已刪）
    src = (__import__("pathlib").Path("paulshaclaw/cli.py")).read_text(encoding="utf-8")
    assert "paulshaclaw.deck" not in src and "paulshaclaw.coordinator" not in src
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_psc_cli_shim.py -v`
Expected: FAIL（cli.py 仍 import paulshaclaw.deck/coordinator）

- [ ] **Step 3: 改 cli.py 為 cortex shim**

`paulshaclaw/cli.py`：coordinator/deck/monitor 統一委派 `paulsha_cortex.cli`，cortex 缺席時 tombstone：

```python
_USAGE = "usage: psc {coordinator|deck|monitor} <args...>\n"
_CORTEX_MOVED = (
    "psc {sub} 已由 paulsha-cortex 提供。\n"
    "安裝：pipx install git+https://github.com/hamanpaul/paulsha-cortex\n"
)
_CORTEX_SUBS = {"coordinator", "deck", "monitor"}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    head = args[0] if args else None
    rest = args[1:]
    if head == "memory":
        sys.stderr.write(_MEMORY_MOVED)
        return 2
    if head in _CORTEX_SUBS:
        try:
            from paulsha_cortex.cli import main as cortex_main
        except ImportError:
            sys.stderr.write(_CORTEX_MOVED.format(sub=head))
            return 2
        return int(cortex_main([head, *rest]) or 0)
    sys.stderr.write(_USAGE)
    return 2
```

（保留既有 `_MEMORY_MOVED`。cortex CLI 傘狀入口本身即認 `coordinator`/`deck`/`monitor` 子命令，故傳 `[head, *rest]`。）

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_psc_cli_shim.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/cli.py tests/test_psc_cli_shim.py
git commit -m "feat: psc coordinator|deck|monitor 改 cortex thin shim（未裝 tombstone）"
```

---

### Task 4: 刪除 5 包 + 遷出測試 + scripts/workflow

**Files:**
- Delete: `paulshaclaw/{persona,coordinator,control,deck,monitor}/`
- Delete: `tests/test_{persona,coordinator,control,deck,stage4_persona,stage9}*`、`test_start_manager_service.py`
- Delete: `scripts/coordinator/`、`scripts/service-manager.sh`、`.github/workflows/persona-scope.yml`

**Interfaces:**
- Consumes: Task 2/3 已無 runtime 消費者殘留
- Produces: 5 包與其測試/腳本自主 repo 移除；grep 清零

- [ ] **Step 1: 刪包與遷出物**

```bash
cd ~/prj_pri/paulshaclaw
git rm -r paulshaclaw/persona paulshaclaw/coordinator paulshaclaw/control paulshaclaw/deck paulshaclaw/monitor
git rm tests/test_persona_*.py tests/test_coordinator_*.py tests/test_control_*.py \
       tests/test_deck_*.py tests/test_stage4_persona_contract.py tests/test_stage9_*.py \
       tests/test_start_manager_service.py
git rm -r scripts/coordinator scripts/service-manager.sh .github/workflows/persona-scope.yml
```

- [ ] **Step 2: grep 清零（含相對 import）**

```bash
grep -rn 'paulshaclaw\.\(persona\|coordinator\|control\|deck\|monitor\)\|from \.\.\(persona\|coordinator\|control\|deck\|monitor\)' paulshaclaw --include='*.py' | grep -v __pycache__ || echo CLEAN
```

Expected: `CLEAN`（若有殘留，多半是漏改的相對 import 或間接引用——逐一處理；`psc` shim 對 cortex 的 import 不算殘留，那是 `paulsha_cortex`）

- [ ] **Step 3: 全測試（主 repo 剩餘）跑綠**

Run: `python -m pytest tests/ -q -x`
Expected: 全 PASS（W7 整合測試改線見 Task 5；若此步因 W7 import 已刪的 coordinator 而 FAIL，先跳過該檔至 Task 5）

- [ ] **Step 4: Commit**

```bash
git commit -m "feat!: 刪除 persona/coordinator/control/deck/monitor（已遷入 paulsha-cortex）"
```

---

### Task 5: deploy/planner + start.sh + W7 整合測試改線

**Files:**
- Modify: `paulshaclaw/deploy/planner.py`（移除 manager 模板）、`scripts/start.sh`（manager/monitor 改指 cortex）
- Delete: `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.{service,timer}.tmpl`
- Modify: W7 整合測試（改 import cortex 或移除）

**Interfaces:**
- Produces: 主 repo 不再自出 manager 單元、start.sh 委派 cortex install/enable

- [ ] **Step 1: 移除 deploy planner manager 模板引用**

`paulshaclaw/deploy/planner.py`：刪除 line 119-163 的 manager service/timer/env 模板條目（改由 cortex `install service` 出貨）；`git rm` 對應 `.tmpl`。

- [ ] **Step 2: start.sh manager/monitor 改指 cortex**

`scripts/start.sh`：
- `start_manager_service()` 的 `install-manager-units.sh` 引用改為 `cortex install service --repo-root "$REPO"`（cortex 一次裝 manager+monitor）；移除 `source service-manager.sh`（已刪）。
- Stage 9 monitor 段 `python -m paulshaclaw.monitor` → 移除（monitor 現由 `cortex install service` 的 monitor unit 常駐，start.sh 只 `systemctl --user enable/start`）。

- [ ] **Step 3: W7 整合測試改線**

W7 整合測試（原 `from paulshaclaw.coordinator.autonomy import …` 驗 deck compile 產出可解析）——deck 與 coordinator 皆已在 cortex，改 `from paulsha_cortex.coordinator.autonomy import …` + `from paulsha_cortex.deck …`，續留主 repo 作**跨包消費面 smoke**（驗主 repo 裝了 cortex 後 deck→manager 契約仍通）。

- [ ] **Step 4: 跑測試 + start.sh 語法檢查**

Run: `python -m pytest tests/ -q && bash -n scripts/start.sh && echo "start.sh syntax ok"`
Expected: 全 PASS + syntax ok

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/deploy scripts/start.sh tests/
git commit -m "refactor: deploy/planner 去 manager 模板、start.sh 委派 cortex install、W7 改線"
```

---

### Task 6: 三個對齊測試（主 repo 為契約交會點）

**Files:**
- Create: `tests/test_cortex_alignment.py`

**Interfaces:**
- Consumes: 同裝的 `paulsha_hippo.lib.lifecycle.schema`、`paulsha_cortex.persona.contract`、`paulsha_cortex.config.paths`、主 repo `config.paths`
- Produces: PHASES 相等、paths 等價、cortex 零 hippo 依賴斷言（deck↔persona 已為 cortex 內部測試，主 repo 僅 smoke）

- [ ] **Step 1: 寫測試**

```python
# tests/test_cortex_alignment.py
def test_phases_equal_across_hippo_and_cortex():
    from paulsha_hippo.lib.lifecycle.schema import PHASES as HIPPO
    from paulsha_cortex.persona.contract import PHASES as CORTEX
    assert tuple(CORTEX) == tuple(HIPPO)


def test_paths_equivalence(monkeypatch, tmp_path):
    from paulshaclaw.config import paths as claw
    from paulsha_cortex.config import paths as cortex
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path / "ctl"))
    monkeypatch.setenv("PSC_SPECS_ROOT", str(tmp_path / "spc"))
    assert claw.control_root() == cortex.control_root()
    assert claw.specs_root() == cortex.specs_root()


def test_cortex_has_no_hippo_dependency():
    import subprocess, sys, json
    out = subprocess.run(
        [sys.executable, "-m", "pip", "show", "paulsha-cortex"],
        capture_output=True, text=True,
    ).stdout
    requires = next((l for l in out.splitlines() if l.lower().startswith("requires:")), "Requires:")
    assert "paulsha-hippo" not in requires
```

- [ ] **Step 2: 跑測試確認通過**

Run: `python -m pytest tests/test_cortex_alignment.py -v`
Expected: 全 PASS（PHASES 兩邊相等；paths 五個 root env 覆寫等價——如有第 3-5 個 root 一併加斷言；cortex Requires 無 hippo）

- [ ] **Step 3: Commit**

```bash
git add tests/test_cortex_alignment.py
git commit -m "test: 三對齊測試（PHASES 相等/paths 等價/cortex 零 hippo）"
```

---

### Task 7: import 面 CI + docs + PR

**Files:**
- Create/Modify: `.github/workflows/`（import 面檢查）、`CLAUDE.md`、`README.md`

**Interfaces:**
- Produces: import 面 CI 守 `cortex-consumer` 允許清單；docs 反映 operator-shell 終態

- [ ] **Step 1: import 面 CI 檢查**

新增（或延用既有 AST lint）workflow step：掃主 repo 非測試碼對 `paulsha_cortex` 的 import，出現 `control.client` + `cli` shim 以外者 FAIL；`paulshaclaw.{persona,coordinator,control,deck,monitor}` 任何殘留 FAIL；`paulsha_hippo` runtime import FAIL（tests 僅限 PHASES 對齊）。

- [ ] **Step 2: docs 更新（R-18 同 PR）**

- `CLAUDE.md`：Stage 4 persona／manager 段改指 paulsha-cortex；命名系統補 `paulsha-cortex`；path split 註記 control/specs 由 cortex 消費。
- `README.md`：主 repo 定位改「operator shell」；治理平面章節指向 cortex。

- [ ] **Step 3: 全測試 + 冒煙**

Run: `python -m pytest tests/ -q && psc coordinator --help >/dev/null 2>&1; echo "psc shim exit=$?"`
Expected: 全 PASS；`psc coordinator` 委派 cortex（已裝 → 0）

- [ ] **Step 4: push + PR（不 merge）**

```bash
git push
gh pr create --fill --label policy-exempt:issue-link --label skip-changelog
```

PR body：`Closes` 不用（#232 為 umbrella）；引用 `#232`。**BREAKING** 註記於 body。**不 merge**——orchestrator 跑 codex 對抗審查 + fresh-install 後當 merge gate。Plan 3（E2E + cutover）於本刀 merge 後執行。
