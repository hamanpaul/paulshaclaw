# paulsha-cortex Repo 建立與遷入實作計劃（#232 / openspec tasks §1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `hamanpaul/paulsha-cortex` repo，遷入 persona/coordinator/control 三包與測試，完成 A′ 三條剪線（PHASES 自帶／idle vendor／paths 自帶），產出可 pin 的 commit SHA。

**Architecture:** 依 `docs/superpowers/specs/2026-07-07-cortex-extraction-design.md` 與 openspec change `cortex-extraction`。本計劃只涵蓋 tasks.md §1（cortex repo 內工作）；§2–§5 主 repo 遷移刀待本計劃產出 pin SHA（gate 1.9）後另出計劃。

**Tech Stack:** Python 3.10+（CI 3.12）、pytest、gh CLI、paulsha-conventions 1.0.12（reusable workflow）、systemd --user units。

## Global Constraints

- 新 repo 首發為 **private**；轉 public 前必過 deident sanitize（R-21）。
- `.paul-project.yml` 宣告 `tier: shareable`（R-21 由 conventions 引擎承接，不自製 scanner）。
- conventions 引擎 pin：`58290153a400926851afa0f1794236e7669847c6`（v1.0.12，與主 repo `policy-check.yml` 相同）。
- agent 檔採 symlink 模式（R-14）：AGENTS.md／GEMINI.md／.github/copilot-instructions.md → CLAUDE.md。
- 所有文件 zh-tw；commit 訊息 conventional（zh-tw 主題）；分支 slug 不得含小數點。
- **cortex 對 paulsha-hippo 零依賴**（pyproject dependencies 不得出現 paulsha-hippo）；對主 repo 僅允許 persona/loader.py 的 `paulshaclaw.deck.schema` lazy import（fail-open，勿改寫）。
- 平移來源：主 repo `hamanpaul/paulshaclaw` @ `2e44c1d8f86879418764b7d41c9022c3b023e70e`（下稱 `$SRC`，本機 `~/prj_pri/paulshaclaw`）。
- repo 工作目錄：`~/prj_pri/paulsha-cortex`；全程在 `feature/bootstrap` 分支。
- cortex repo 的 PR 引用主 repo issue（#232、#125）時一律掛 `policy-exempt:issue-link` label（R-17）。

---

### Task 1: 建立 repo 骨架

**Files:**
- Create: GitHub repo `hamanpaul/paulsha-cortex`（from template）
- Create: local clone `~/prj_pri/paulsha-cortex`
- Modify: `pyproject.toml`、`.paul-project.yml`、`CLAUDE.md`

**Interfaces:**
- Consumes: `hamanpaul/new-project-template`（含 `.paul-project.yml`、`policy-check.yml`、`tests.yml`、agent 檔、`VERSION=0.0.0`）
- Produces: 可 push 的 clone + `feature/bootstrap` 分支；package 名 `paulsha_cortex`；console script 名 `cortex`

- [ ] **Step 1: 從 template 建 private repo**

```bash
gh repo create hamanpaul/paulsha-cortex \
  --template hamanpaul/new-project-template \
  --private \
  --description "agent 治理平面：manager 派工決策 + persona scope 護欄 + control 檔案契約控制面"
```

Expected: 輸出 `https://github.com/hamanpaul/paulsha-cortex`

- [ ] **Step 2: clone、開分支、驗 symlink**

```bash
git clone git@github.com:hamanpaul/paulsha-cortex.git ~/prj_pri/paulsha-cortex
cd ~/prj_pri/paulsha-cortex && git checkout -b feature/bootstrap
ls -la AGENTS.md GEMINI.md .github/copilot-instructions.md
```

Expected: 三者皆為指向 CLAUDE.md 的 symlink（copilot 為 `-> ../CLAUDE.md`）。若被 template 產生器展開為一般檔案：

```bash
rm AGENTS.md GEMINI.md .github/copilot-instructions.md
ln -s CLAUDE.md AGENTS.md && ln -s CLAUDE.md GEMINI.md && ln -s ../CLAUDE.md .github/copilot-instructions.md
```

- [ ] **Step 3: 寫 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "paulsha-cortex"
dynamic = ["version"]
requires-python = ">=3.10"
description = "agent 治理平面：manager 派工 + persona 護欄 + control 檔案契約"
dependencies = []

[project.scripts]
cortex = "paulsha_cortex.cli:main"

[tool.setuptools.dynamic]
version = {file = "VERSION"}

[tool.setuptools.packages.find]
where = ["."]
include = ["paulsha_cortex*"]

[tool.setuptools.package-data]
"paulsha_cortex.deploy" = ["templates/*.tmpl"]
"paulsha_cortex" = [
    "persona/personas.yaml",
    "scripts/*.sh",
    "scripts/*.py",
    "scripts/hooks/*.json",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

（`dependencies = []` 是 A′ 零依賴的機器可驗形式。）

- [ ] **Step 4: `.paul-project.yml` 宣告 tier 與 policy pin 核對**

在 `.paul-project.yml` 補 `tier: shareable`；確認 `.github/workflows/policy-check.yml` 的引擎 pin 為 `58290153a400926851afa0f1794236e7669847c6`。

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: paulsha-cortex 骨架（pyproject/tier/symlink）"
```

---

### Task 2: 三包平移與 import 改寫

**Files:**
- Create: `paulsha_cortex/{persona,coordinator,control}/`（自 `$SRC/paulshaclaw/` 平移）
- Create: `paulsha_cortex/__init__.py`

**Interfaces:**
- Consumes: `$SRC` checkout（pin `2e44c1d8`）
- Produces: `paulsha_cortex.persona`、`paulsha_cortex.coordinator`、`paulsha_cortex.control` 三個可 import 子包（此時尚依賴 hippo/config，Task 3–5 剪線）

- [ ] **Step 1: 以 pinned SHA 匯出來源**

```bash
cd ~/prj_pri/paulshaclaw && git worktree add /tmp/claw-src 2e44c1d8f86879418764b7d41c9022c3b023e70e
```

- [ ] **Step 2: 複製三包（排除 __pycache__）**

```bash
cd ~/prj_pri/paulsha-cortex && mkdir -p paulsha_cortex
for pkg in persona coordinator control; do
  rsync -a --exclude '__pycache__' /tmp/claw-src/paulshaclaw/$pkg/ paulsha_cortex/$pkg/
done
touch paulsha_cortex/__init__.py
```

- [ ] **Step 3: 絕對 import 改寫（僅四個子包名；勿碰 paulshaclaw.deck）**

```bash
grep -rln 'paulshaclaw\.\(persona\|coordinator\|control\|config\)' paulsha_cortex/ | \
  xargs sed -i 's/paulshaclaw\.\(persona\|coordinator\|control\|config\)/paulsha_cortex.\1/g'
```

- [ ] **Step 4: 驗證 deck lazy import 未被誤改**

```bash
grep -rn 'paulshaclaw' paulsha_cortex/
```

Expected: 僅剩 `paulsha_cortex/persona/loader.py` 一處 `from paulshaclaw.deck.schema import ...`（fail-open 契約，保留原樣）。出現其他 `paulshaclaw` 引用即為漏改，逐一處理。

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: 平移 persona/coordinator/control 三包（src pin 2e44c1d8）"
```

---

### Task 3: 剪線一——PHASES 自帶

**Files:**
- Modify: `paulsha_cortex/persona/contract.py:1-10`
- Test: `tests/test_phases_constant.py`

**Interfaces:**
- Produces: `paulsha_cortex.persona.contract.PHASES: tuple[str, ...]`（7 元素，Stage 3 生命週期詞彙表；主 repo 對齊測試將驗其與 hippo 相等）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_phases_constant.py
def test_phases_is_frozen_stage3_vocabulary():
    from paulsha_cortex.persona.contract import PHASES
    assert PHASES == ("research", "define", "plan", "build", "verify", "review", "ship")


def test_no_hippo_import():
    import paulsha_cortex.persona.contract as m
    import inspect
    assert "paulsha_hippo" not in inspect.getsource(m)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_phases_constant.py -v`
Expected: FAIL（`ModuleNotFoundError: paulsha_hippo` 或 source 內含 `paulsha_hippo`）

- [ ] **Step 3: 改 contract.py**

刪除：

```python
from paulsha_hippo.lib.lifecycle import schema as lifecycle_schema


PHASES = lifecycle_schema.PHASES
```

改為：

```python
# Stage 3 生命週期詞彙表（語意凍結）；與 paulsha_hippo.lib.lifecycle.schema.PHASES
# 的相等性由主 repo（paulshaclaw）對齊測試守——契約交會點在消費端，cortex 零 hippo 依賴。
PHASES = (
    "research",
    "define",
    "plan",
    "build",
    "verify",
    "review",
    "ship",
)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_phases_constant.py -v`
Expected: PASS ×2

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: PHASES 常數自帶，剪除 hippo lifecycle import（A′ 剪線 1/3）"
```

---

### Task 4: 剪線二——idle vendor

**Files:**
- Create: `paulsha_cortex/lib/__init__.py`、`paulsha_cortex/lib/idle.py`
- Modify: `paulsha_cortex/coordinator/manager.py:11`
- Test: `tests/test_idle.py`

**Interfaces:**
- Produces: `paulsha_cortex.lib.idle.is_idle(max_load: float = 1.0, probe=os.getloadavg) -> bool`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_idle.py
import pytest
from paulsha_cortex.lib.idle import is_idle


def test_idle_when_load_below_max():
    assert is_idle(max_load=1.0, probe=lambda: (0.5, 0.0, 0.0)) is True


def test_busy_when_load_above_max():
    assert is_idle(max_load=1.0, probe=lambda: (2.0, 0.0, 0.0)) is False


def test_non_tuple_probe_rejected():
    with pytest.raises(TypeError):
        is_idle(probe=lambda: [0.5])


def test_fail_safe_on_oserror():
    def boom():
        raise OSError
    assert is_idle(probe=boom) is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_idle.py -v`
Expected: FAIL（`ModuleNotFoundError: paulsha_cortex.lib`）

- [ ] **Step 3: vendor idle.py**

`paulsha_cortex/lib/idle.py`（vendored from paulsha-hippo `paulsha_hippo/lib/idle.py` @ v0.1.0 `30ebbbd5`，行為零改動）：

```python
import os
from typing import Callable, Tuple


def is_idle(max_load: float = 1.0, probe: Callable[[], Tuple[float, ...]] = os.getloadavg) -> bool:
    """Return True when system is considered idle using the 1-minute load average.

    probe must be a callable that returns a tuple (like os.getloadavg()).
    Tuples are required; lists or other sequence types are rejected with TypeError.
    Scalars are not supported and will raise TypeError. If the load cannot be
    determined due to OSError, AttributeError, or IndexError, the function
    fails safe and returns True.
    """
    try:
        result = probe()
        # Only accept tuple-style results matching os.getloadavg()
        if not isinstance(result, tuple):
            raise TypeError("probe must return a tuple like os.getloadavg()")
        load = float(result[0])
        return load <= float(max_load)
    except (OSError, AttributeError, IndexError):
        # fail-safe: if we can't determine load, allow running
        return True
```

並將 `paulsha_cortex/coordinator/manager.py` 的 `from paulsha_hippo.lib import idle` 改為：

```python
from paulsha_cortex.lib import idle
```

- [ ] **Step 4: 跑測試確認通過；全 repo grep hippo 清零**

Run: `python -m pytest tests/test_idle.py -v && grep -rn 'paulsha_hippo' paulsha_cortex/ | wc -l`
Expected: PASS ×4；grep 計數 `0`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: vendor lib/idle（hippo 30ebbbd5），剪除 hippo import（A′ 剪線 2/3）"
```

---

### Task 5: 剪線三——paths 模組自帶

**Files:**
- Create: `paulsha_cortex/config/__init__.py`、`paulsha_cortex/config/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `paulsha_cortex.config.paths` 提供 `control_root()`、`coordinator_root()`、`specs_root()`、`repo_root()`、`worktree_root()`（簽名與主 repo facade 相同；Task 2 的 sed 已把三包內 `paulshaclaw.config` 指到這裡）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_paths.py
from pathlib import Path
from paulsha_cortex.config import paths


def test_defaults_under_agents(monkeypatch):
    for var in ("PSC_AGENTS_ROOT", "PSC_CONTROL_ROOT", "PSC_COORDINATOR_ROOT", "PSC_SPECS_ROOT"):
        monkeypatch.delenv(var, raising=False)
    home = Path.home()
    assert paths.control_root() == home / ".agents" / "control"
    assert paths.coordinator_root() == home / ".agents" / "coordinator"
    assert paths.specs_root() == home / ".agents" / "specs"


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path / "ctl"))
    assert paths.control_root() == tmp_path / "ctl"


def test_repo_root_env_then_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_REPO_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path
    monkeypatch.delenv("PSC_REPO_ROOT")
    assert paths.repo_root() == Path.cwd()


def test_worktree_root_is_repo_sibling(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("PSC_REPO_ROOT", str(tmp_path / "myrepo"))
    assert paths.worktree_root() == tmp_path / "myrepo-worktrees"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL（`ModuleNotFoundError: paulsha_cortex.config`）

- [ ] **Step 3: 寫 paths.py**

```python
"""cortex 路徑契約——鏡射主 repo paulshaclaw.config.paths 的治理平面子集。

env 覆寫契約與主 repo 相同（PSC_* 前綴）；等價性由主 repo 對齊測試守。
與主 repo facade 的唯一語意差異：repo_root() 無 checkout 相對預設
（安裝進 site-packages 後 __file__ 相對路徑必壞——hippo 審查修正 #3 同型），
改為 PSC_REPO_ROOT env → 其次 Path.cwd()（daemon 由 systemd EnvironmentFile 注入）。
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def _resolve_root(name: str, default: Path) -> Path:
    return _env_path(name) or default


def agents_root() -> Path:
    return _resolve_root("PSC_AGENTS_ROOT", Path.home() / ".agents")


def control_root() -> Path:
    return _resolve_root("PSC_CONTROL_ROOT", agents_root() / "control")


def coordinator_root() -> Path:
    return _resolve_root("PSC_COORDINATOR_ROOT", agents_root() / "coordinator")


def specs_root() -> Path:
    return _resolve_root("PSC_SPECS_ROOT", agents_root() / "specs")


def repo_root() -> Path:
    return _resolve_root("PSC_REPO_ROOT", Path.cwd())


def _canonical_repo_root(repo: Path) -> Path:
    if repo.parent.name == ".worktrees":
        return repo.parent.parent
    return repo


def worktree_root() -> Path:
    """coordinator 派工 worktree 池——鏡射 scripts/using-git-worktrees.sh 契約。

    預設一律為 sibling `<repo>-worktrees`；僅 PSC_WORKTREE_ROOT 顯式覆寫可改。
    """
    override = _env_path("PSC_WORKTREE_ROOT")
    if override is not None:
        return override
    repo = _canonical_repo_root(repo_root())
    return repo.parent / f"{repo.name}-worktrees"
```

- [ ] **Step 4: 跑測試確認通過；三包 import 冒煙**

Run: `python -m pytest tests/test_paths.py -v && python -c "import paulsha_cortex.coordinator.cli, paulsha_cortex.persona.loader, paulsha_cortex.control.client; print('ok')"`
Expected: PASS ×4；輸出 `ok`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: cortex 自帶 paths 模組（A′ 剪線 3/3；repo_root 改 env→cwd 語意）"
```

---

### Task 6: 測試與 runtime script 平移、全綠

**Files:**
- Create: `tests/`（自 `$SRC/tests/` 平移 25 檔）
- Create: `paulsha_cortex/scripts/{psc-relay-hook.sh,coordinator_telegram_notifier.py,dispatch-stage-wave-a.sh,copilot-stage-worker.sh}`、`paulsha_cortex/scripts/hooks/{claude,codex,copilot}.json`

**Interfaces:**
- Consumes: Task 2–5 的三包與剪線結果
- Produces: cortex 全測試綠（含平移的 flock 單寫者測試——spec §4.6 不變量）；relay hook 與 hook json 隨包出貨（`test_coordinator_relay_hook.py`、`test_coordinator_hook_templates.py` 的依賴）

- [ ] **Step 1: 平移 runtime scripts（排除 install-manager-units.sh——已由 Task 8 installer 取代）**

```bash
cd ~/prj_pri/paulsha-cortex && mkdir -p paulsha_cortex/scripts/hooks
cp /tmp/claw-src/scripts/coordinator/psc-relay-hook.sh \
   /tmp/claw-src/scripts/coordinator/coordinator_telegram_notifier.py \
   /tmp/claw-src/scripts/coordinator/dispatch-stage-wave-a.sh \
   /tmp/claw-src/scripts/coordinator/copilot-stage-worker.sh paulsha_cortex/scripts/
cp /tmp/claw-src/scripts/coordinator/hooks/*.json paulsha_cortex/scripts/hooks/
```

- [ ] **Step 2: 平移測試檔並改 import**

```bash
cp /tmp/claw-src/tests/test_coordinator_*.py /tmp/claw-src/tests/test_persona_*.py \
   /tmp/claw-src/tests/test_control_*.py /tmp/claw-src/tests/test_start_manager_service.py \
   /tmp/claw-src/tests/test_stage4_persona_contract.py tests/
sed -i 's/paulshaclaw\.\(persona\|coordinator\|control\|config\)/paulsha_cortex.\1/g' tests/test_*.py
```

- [ ] **Step 3: 修 script 路徑常數（三個測試的檔案路徑指向新位置）**

改 `tests/test_coordinator_relay_hook.py`：`HOOK = "scripts/coordinator/psc-relay-hook.sh"` → `HOOK = "paulsha_cortex/scripts/psc-relay-hook.sh"`。
改 `tests/test_coordinator_hook_templates.py`：`HOOKS` 常數（指向 `scripts/coordinator/hooks`）→ `paulsha_cortex/scripts/hooks`。
改 `tests/test_start_manager_service.py`：service-manager.sh 路徑 → `paulsha_cortex/scripts/service-manager.sh`（Task 8 產出；此測試依賴 Task 8，暫標 `@pytest.mark.skip(reason="Task 8")`，Task 8 Step 4 解除）。

```bash
grep -rn 'paulshaclaw\|scripts/coordinator' tests/ || echo CLEAN
```

Expected: `CLEAN`，或僅剩引用 deck 的測試——deck 留主 repo，這類測試（若有）不隨包遷入，逐一確認並移除。

- [ ] **Step 4: 全測試跑綠**

Run: `python -m pytest tests/ -x -q`
Expected: 全 PASS（約 25 檔 + Task 3–5 新增 3 檔）。`test_start_manager_service.py` 若因 Task 8 未完成而 FAIL，暫標 `@pytest.mark.skip(reason="Task 8")` 並於 Task 8 Step 4 移除。

- [ ] **Step 5: 確認 flock 單寫者測試在列**

Run: `python -m pytest tests/test_coordinator_manager_daemon.py -q -k lock`
Expected: 至少 1 個 lock 相關測試 PASS（spec §4.6 不變量隨包平移的證據）

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "test: 平移三包測試 25 檔 + runtime scripts，改線 paulsha_cortex"
```

---

### Task 7: CLI console script

**Files:**
- Create: `paulsha_cortex/cli.py`
- Test: `tests/test_cli_entry.py`

**Interfaces:**
- Consumes: `paulsha_cortex.coordinator.cli:main(argv: Sequence[str] | None) -> int`
- Produces: console script `cortex`——`cortex install service …` 走 installer（Task 8）、其餘子命令原樣透傳 coordinator CLI（Plan 2 的 `psc coordinator` shim 也直接 import 此模組）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_cli_entry.py
from paulsha_cortex.cli import main


def test_delegates_to_coordinator_cli(monkeypatch):
    seen = {}

    def fake_main(argv=None):
        seen["argv"] = list(argv or [])
        return 0

    monkeypatch.setattr("paulsha_cortex.coordinator.cli.main", fake_main)
    assert main(["status"]) == 0
    assert seen["argv"] == ["status"]


def test_unknown_empty_shows_usage(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_cli_entry.py -v`
Expected: FAIL（`ModuleNotFoundError: paulsha_cortex.cli`）

- [ ] **Step 3: 寫 cli.py**

```python
"""cortex 傘狀入口：install 子樹走 installer，其餘透傳 coordinator CLI。"""
from __future__ import annotations

import sys
from typing import Sequence

_USAGE = "usage: cortex {install service|<coordinator subcommand>} <args...>\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(_USAGE)
        return 2
    if args[0] == "install":
        from paulsha_cortex.deploy.installer import main as install_main

        return int(install_main(args[1:]) or 0)
    from paulsha_cortex.coordinator.cli import main as coordinator_main

    return int(coordinator_main(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_cli_entry.py -v`
Expected: PASS ×2

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: cortex console script（install 子樹 + coordinator 透傳）"
```

---

### Task 8: service 出貨——service-manager.sh 參數化 + install service

**Files:**
- Create: `paulsha_cortex/scripts/service-manager.sh`（自 `$SRC/scripts/service-manager.sh` 平移改造）
- Create: `paulsha_cortex/deploy/__init__.py`、`paulsha_cortex/deploy/installer.py`、`paulsha_cortex/deploy/templates/manager.service.tmpl`、`manager.timer.tmpl`
- Test: `tests/test_install_service.py`

**Interfaces:**
- Consumes: `$SRC/scripts/service-manager.sh`、`$SRC/paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.{service,timer}.tmpl`
- Produces: `cortex install service [--instance NAME] [--interval SECONDS]`——冪等 render→copy→daemon-reload→enable（spec §5 cutover 協議的 install 端）

- [ ] **Step 1: 平移並改造 service-manager.sh**

```bash
mkdir -p paulsha_cortex/scripts
cp /tmp/claw-src/scripts/service-manager.sh paulsha_cortex/scripts/service-manager.sh
```

三處改造（其餘邏輯——lock 認養、startup 檢查、legacy timer 停用——原樣保留）：

1. module 名：`is_live_manager_pid` 內 cmdline 比對 `paulshaclaw.coordinator.manager_daemon` → `paulsha_cortex.coordinator.manager_daemon`；`start_manager_loop` 內 `-m paulshaclaw.coordinator.manager_daemon` → `-m paulsha_cortex.coordinator.manager_daemon`。
2. 移除 checkout 假設：`REPO` 推導段（`REPO="$(cd "$_psc_service_dir/.." && pwd)"`）刪除；`PY` 預設改 `PY=$(command -v python3)`；`PYTHONPATH="$REPO"` 前綴刪除（pip 安裝後不需要）。
3. specs 來源：`--specs-dir "$REPO/docs/superpowers/specs"` 改 `--specs-dir "${PSC_MANAGER_SPECS_DIR:-$HOME/.agents/specs}"`。

- [ ] **Step 2: 寫 unit 模板**

`paulsha_cortex/deploy/templates/manager.service.tmpl`：

```ini
[Unit]
Description=__INSTANCE__ persona manager service (paulsha-cortex)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
EnvironmentFile=-%h/.agents/core/runtime/__INSTANCE__.env
EnvironmentFile=-%h/.agents/core/runtime/__INSTANCE__-manager.env
ExecStart=/usr/bin/env bash __SERVICE_SCRIPT__
KillMode=control-group
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

`manager.timer.tmpl` 自 `$SRC` 模板原樣平移（僅 Description 加 cortex 註記）。

- [ ] **Step 3: 寫失敗測試 + installer**

```python
# tests/test_install_service.py
from paulsha_cortex.deploy.installer import render_units


def test_render_substitutes_instance_and_script(tmp_path):
    units = render_units(instance="alpha", interval=120)
    service = units["alpha-manager.service"]
    assert "__INSTANCE__" not in service and "__SERVICE_SCRIPT__" not in service
    assert "alpha persona manager service" in service
    timer = units["alpha-manager.timer"]
    assert "OnUnitActiveSec=120" in timer


def test_install_is_idempotent(tmp_path, monkeypatch):
    from paulsha_cortex.deploy import installer
    monkeypatch.setattr(installer, "_systemctl_available", lambda: False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert installer.main(["service", "--instance", "beta"]) == 0
    first = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert installer.main(["service", "--instance", "beta"]) == 0
    second = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert first == second
```

Run: `python -m pytest tests/test_install_service.py -v` → Expected: FAIL（module 不存在）

`paulsha_cortex/deploy/installer.py`：

```python
"""cortex install service——render→copy→daemon-reload→enable，冪等。

吸收主 repo scripts/coordinator/install-manager-units.sh 的職責；
systemd 不可用時僅落檔並提示（G3 決策樹：先驗證再選路）。
停用舊單元屬 cutover 操作（Plan 2），不在 install 職責內。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Sequence


def _template(name: str) -> str:
    return (resources.files("paulsha_cortex.deploy") / "templates" / name).read_text()


def _service_script_path() -> Path:
    return Path(str(resources.files("paulsha_cortex") / "scripts" / "service-manager.sh"))


def render_units(instance: str, interval: int) -> dict[str, str]:
    service = _template("manager.service.tmpl").replace("__INSTANCE__", instance)
    service = service.replace("__SERVICE_SCRIPT__", str(_service_script_path()))
    timer = _template("manager.timer.tmpl").replace("__INSTANCE__", instance)
    timer = re.sub(r"^OnUnitActiveSec=.*$", f"OnUnitActiveSec={interval}", timer, flags=re.M)
    return {f"{instance}-manager.service": service, f"{instance}-manager.timer": timer}


def _systemctl_available() -> bool:
    if shutil.which("systemctl") is None:
        return False
    probe = subprocess.run(
        ["systemctl", "--user", "show-environment"], capture_output=True
    )
    return probe.returncode == 0


def install_service(instance: str, interval: int) -> int:
    home = Path.home()
    unit_dir = home / ".config" / "systemd" / "user"
    runtime_dir = home / ".agents" / "core" / "runtime"
    for d in (unit_dir, runtime_dir, home / ".agents" / "specs"):
        d.mkdir(parents=True, exist_ok=True)
    for name, content in render_units(instance, interval).items():
        (unit_dir / name).write_text(content)
    env_file = runtime_dir / f"{instance}-manager.env"
    if not env_file.exists():
        env_file.write_text("")
    if not _systemctl_available():
        print(f"systemd 不可用：單元已落檔 {unit_dir}，請改用 service-manager.sh 前景模式")
        return 0
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", f"{instance}-manager.timer"], check=True)
    print(f"installed: {instance}-manager.{{service,timer}}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cortex install")
    sub = parser.add_subparsers(dest="target", required=True)
    svc = sub.add_parser("service")
    svc.add_argument("--instance", default="paulshaclaw")
    svc.add_argument("--interval", type=int, default=300)
    args = parser.parse_args(argv)
    return install_service(args.instance, args.interval)
```

- [ ] **Step 4: 跑測試確認通過（含解除 Task 6 的 skip）**

Run: `python -m pytest tests/test_install_service.py tests/test_start_manager_service.py -v`
Expected: 全 PASS（`test_start_manager_service.py` 的 script 路徑已指 `paulsha_cortex/scripts/service-manager.sh`，skip 標記移除）

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: cortex install service（冪等）+ service-manager.sh 參數化平移"
```

---

### Task 9: CI——tests 與 persona-scope

**Files:**
- Modify: `.github/workflows/tests.yml`（template 既有，核對 testpaths）
- Create: `.github/workflows/persona-scope.yml`（自 `$SRC/.github/workflows/persona-scope.yml` 平移）

**Interfaces:**
- Produces: R-19 滿足（tests workflow 實跑 pytest）；persona scope CI 於 cortex 續跑（spec DoD 5）

- [ ] **Step 1: 平移 persona-scope workflow 並改 module 路徑**

```bash
cp /tmp/claw-src/.github/workflows/persona-scope.yml .github/workflows/
sed -i 's/paulshaclaw\.persona\.scope_ci/paulsha_cortex.persona.scope_ci/' .github/workflows/persona-scope.yml
```

- [ ] **Step 2: 本地模擬兩個 workflow 的執行命令**

Run: `python -m pytest tests/ -q && python -m paulsha_cortex.persona.scope_ci`
Expected: pytest 全 PASS；scope_ci exit 0

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "ci: tests + persona-scope workflow（R-19／scope CI 續跑）"
```

---

### Task 10: README、push 與 pin SHA（gate 1.9）

**Files:**
- Create: `README.md`
- Modify: `CLAUDE.md`（repo 定位段）

**Interfaces:**
- Produces: 遠端 `feature/bootstrap` 分支 + PR + merge 後 main 的 **pin 用 40 字元 SHA**——主 repo 遷移刀（Plan 2）的動工前置

- [ ] **Step 1: README 骨架**

章節：定位（治理平面三件套 + 與 paulshaclaw/paulsha-hippo 的關係圖）、安裝（`pipx install git+…`）、快速開始（`cortex install service` → `cortex status`）、path 契約（`~/.agents/control`、`PSC_*` env）、誠實狀態表（persona enforcement 現況 `shadow`，enforce 翻牌見 #124）。zh-tw。

- [ ] **Step 2: 乾淨環境安裝冒煙（fresh-install 教訓前置檢查）**

```bash
python -m venv /tmp/cortex-venv && /tmp/cortex-venv/bin/pip install ~/prj_pri/paulsha-cortex -q
/tmp/cortex-venv/bin/cortex --help >/dev/null; echo "exit=$?"
/tmp/cortex-venv/bin/pip show paulsha-cortex | grep -i requires
```

Expected: `exit=2`（usage，尚無子命令）或 0；`Requires:` 為空（零依賴驗證）

- [ ] **Step 3: push、開 PR、merge**

```bash
git push -u origin feature/bootstrap
gh pr create --fill --label policy-exempt:issue-link
```

PR body 引用主 repo `hamanpaul/paulshaclaw#232`（跨 repo 引用，掛 exempt label）。policy 綠後 merge。

- [ ] **Step 4: 記錄 pin SHA**

```bash
git checkout main && git pull --ff-only && git rev-parse HEAD
```

Expected: 40 字元 SHA——填入主 repo openspec `cortex-extraction/tasks.md` 的 1.9 勾選註記，Plan 2（主 repo 遷移刀）以此 SHA 動工。

- [ ] **Step 5: 清理來源 worktree**

```bash
cd ~/prj_pri/paulshaclaw && git worktree remove /tmp/claw-src
```
