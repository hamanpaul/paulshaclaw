# paulsha-cortex Plan 1b：deck + monitor 進 cortex 實作計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `deck`（任務定義/combo 編譯）與 `monitor`（任務狀態快照）平移進 paulsha-cortex，補齊 `cortex deck|monitor` CLI、monitor 的兩份 registry merge、monitor 併入 `install service`，產出 Plan 2 用的新 pin SHA。

**Architecture:** 依設計 spec `2026-07-07-cortex-extraction-design.md` §R1（R1.3 scope、R1.6 registry 契約、R1.11 plan 鏈）。deck/monitor 僅 import `config.paths`（cortex 補齊 `config_path`/`run_root`/`project_config_root` 即零剪線）；deck 對 coordinator 的契約同包後為 intra-cortex；monitor 監控集 = 手寫 `project-cortex.yaml` ⊍ hippo `project-hippo.yaml`（realpath 去重）。**行為保持為主，閉環（feedback/retry/enforcement）非本 scope。**

**Tech Stack:** Python 3.10+（CI 3.12）、pytest、gh CLI、systemd --user units、PyYAML（monitor 既用）。

## Global Constraints

- 工作 repo：`~/prj_pri/paulsha-cortex`，全程在 `feature/plan1b-deck-monitor` 分支（自 main 開，main 現為 Plan 1 merge 後 `2e67100`）。**不 merge PR**——orchestrator 當 merge gate。
- 平移來源：主 repo `hamanpaul/paulshaclaw` @ `2e44c1d8f86879418764b7d41c9022c3b023e70e`（下稱 `$SRC`）；唯讀。
- **零依賴**：pyproject `dependencies` 不得新增（deck/monitor 只需 `config.paths`，PyYAML 已由 monitor 帶——確認它進 dependencies 或改為 stdlib 解析，見 Task 4）；runtime 不 import `paulsha_hippo`；讀 `project-hippo.yaml` 為**檔案契約**非 import hippo。
- **去識別化（tier: shareable）**：平移檔不得含 `/home/paul_chen`、`paul_chen`、雇主/廠商名；push 前 `grep -rnE '/home/paul_chen|paul_chen' paulsha_cortex tests` 必 CLEAN。
- **唯一允許的 paulshaclaw 殘留**：無（deck/monitor 全改 `paulsha_cortex.*`；persona loader 的 deck import 也改同包，見 Task 9）。
- 所有文件與 commit 一律 zh-tw；conventional commit；每個 Task 一個以上 commit。
- 分支 slug 不得含小數點；cortex PR 引用主 repo issue 掛 `policy-exempt:issue-link` + `skip-changelog`。
- registry canonical base dir = `~/.agents/config/paulsha/`；manual 讀取順序、realpath 去重、缺檔行為見設計 spec R1.6（本計劃 Task 6/7 實作）。

---

### Task 1: 分支 + 來源 worktree

**Files:**
- Create: local branch `feature/plan1b-deck-monitor`；來源 worktree `/tmp/claw-src`

**Interfaces:**
- Produces: 乾淨分支 + `$SRC` 唯讀 checkout 供平移

- [ ] **Step 1: 開分支**

```bash
cd ~/prj_pri/paulsha-cortex && git checkout main && git pull --ff-only && git checkout -b feature/plan1b-deck-monitor
```

- [ ] **Step 2: 備妥來源 worktree**

```bash
git -C /home/paul_chen/prj_pri/paulshaclaw worktree add /tmp/claw-src 2e44c1d8f86879418764b7d41c9022c3b023e70e
ls /tmp/claw-src/paulshaclaw/deck /tmp/claw-src/paulshaclaw/monitor >/dev/null && echo OK
```

Expected: `OK`

---

### Task 2: cortex paths 補 config_path / run_root / project_config_root

**Files:**
- Modify: `paulsha_cortex/config/paths.py`
- Test: `tests/test_paths.py`（Plan 1 既有，追加）

**Interfaces:**
- Produces: `paths.config_root()`, `paths.config_path(*parts)`, `paths.run_root()`, `paths.project_config_root()`（deck/monitor 與 registry 契約依賴）

- [ ] **Step 1: 追加失敗測試**

```python
# tests/test_paths.py 追加
def test_run_root_default_and_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_RUN_ROOT", raising=False)
    assert paths.run_root() == Path.home() / ".agents" / "run"
    monkeypatch.setenv("PSC_RUN_ROOT", str(tmp_path / "run"))
    assert paths.run_root() == tmp_path / "run"


def test_config_path_default(monkeypatch):
    monkeypatch.delenv("PSC_CONFIG_ROOT", raising=False)
    assert paths.config_path("paulshaclaw.yaml") == Path.home() / ".config" / "paulshaclaw" / "paulshaclaw.yaml"


def test_project_config_root(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_PROJECT_CONFIG_ROOT", raising=False)
    assert paths.project_config_root() == Path.home() / ".agents" / "config" / "paulsha"
    monkeypatch.setenv("PSC_PROJECT_CONFIG_ROOT", str(tmp_path / "pc"))
    assert paths.project_config_root() == tmp_path / "pc"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_paths.py -k "run_root or config_path or project_config_root" -v`
Expected: FAIL（`AttributeError: module ... has no attribute 'run_root'`）

- [ ] **Step 3: 實作（追加至 paths.py 末尾）**

```python
def run_root() -> Path:
    return _resolve_root("PSC_RUN_ROOT", agents_root() / "run")


def config_root() -> Path:
    return _resolve_root("PSC_CONFIG_ROOT", Path.home() / ".config" / "paulshaclaw")


def config_path(*parts: str) -> Path:
    return config_root().joinpath(*parts)


def project_config_root() -> Path:
    return _resolve_root("PSC_PROJECT_CONFIG_ROOT", agents_root() / "config" / "paulsha")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_paths.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulsha_cortex/config/paths.py tests/test_paths.py
git commit -m "feat: paths 補 run_root/config_path/project_config_root（deck/monitor 前置）"
```

---

### Task 3: 平移 deck 套件 + 測試（行為保持）

**Files:**
- Create: `paulsha_cortex/deck/{__init__,schema,compile,verify,cli}.py`
- Create: `tests/test_deck_{schema,compile,verify,data,cli,contract_alignment}.py`

**Interfaces:**
- Consumes: `$SRC/paulshaclaw/deck/**`、`$SRC/tests/test_deck_*.py`
- Produces: `paulsha_cortex.deck`（import `paulsha_cortex.config.paths`、對 coordinator 的契約為 intra-cortex `paulsha_cortex.coordinator.autonomy`）

- [ ] **Step 1: 複製 deck 套件與測試**

```bash
cd ~/prj_pri/paulsha-cortex
rsync -a --exclude __pycache__ /tmp/claw-src/paulshaclaw/deck/ paulsha_cortex/deck/
cp /tmp/claw-src/tests/test_deck_schema.py /tmp/claw-src/tests/test_deck_compile.py \
   /tmp/claw-src/tests/test_deck_verify.py /tmp/claw-src/tests/test_deck_data.py \
   /tmp/claw-src/tests/test_deck_cli.py /tmp/claw-src/tests/test_deck_contract_alignment.py tests/
```

- [ ] **Step 2: import 改寫（deck + 其測試）**

```bash
sed -i 's/paulshaclaw\.\(deck\|coordinator\|config\|persona\)/paulsha_cortex.\1/g' \
  paulsha_cortex/deck/*.py tests/test_deck_*.py
grep -rn 'paulshaclaw' paulsha_cortex/deck tests/test_deck_*.py || echo CLEAN
```

Expected: `CLEAN`（deck schema.py 內對 `coordinator/autonomy.py` 的**註解**若含 `paulshaclaw` 亦一併改；確認無殘留）

- [ ] **Step 3: 跑 deck 測試確認綠**

Run: `python -m pytest tests/test_deck_schema.py tests/test_deck_compile.py tests/test_deck_verify.py tests/test_deck_data.py tests/test_deck_cli.py tests/test_deck_contract_alignment.py -q`
Expected: 全 PASS（deck 測試 import `paulsha_cortex.coordinator.autonomy`——同包已在，intra-cortex 契約成立）

- [ ] **Step 4: Commit**

```bash
git add paulsha_cortex/deck tests/test_deck_*.py
git commit -m "feat: 平移 deck 套件 + 測試（intra-cortex coordinator 契約）"
```

---

### Task 4: 平移 monitor 套件 + 測試（行為保持，配置沿舊）

**Files:**
- Create: `paulsha_cortex/monitor/{__init__,__main__,config,models,parser,scanner,server,service,snapshot,watcher}.py`
- Create: `tests/test_stage9_project_monitor.py`、`tests/test_stage9_project_monitor_service.py`
- Modify: `pyproject.toml`（PyYAML 依賴，見 Step 3）

**Interfaces:**
- Consumes: `$SRC/paulshaclaw/monitor/**`、`$SRC/tests/test_stage9_*.py`
- Produces: `paulsha_cortex.monitor`（`main(argv)`：預設 serve、`--once` 快照；`load_config`、`MonitorConfig(workspaces, socket_path)`、`WorkspaceConfig(path,name)`、`scan_workspaces(config)`）——本 Task **配置仍讀 `paths.config_path("paulshaclaw.yaml")`**（Task 6 才改名）

- [ ] **Step 1: 複製 monitor 套件與測試**

```bash
cd ~/prj_pri/paulsha-cortex
rsync -a --exclude __pycache__ /tmp/claw-src/paulshaclaw/monitor/ paulsha_cortex/monitor/
cp /tmp/claw-src/tests/test_stage9_project_monitor.py \
   /tmp/claw-src/tests/test_stage9_project_monitor_service.py tests/
sed -i 's/paulshaclaw\.\(monitor\|config\)/paulsha_cortex.\1/g' \
  paulsha_cortex/monitor/*.py tests/test_stage9_*.py
grep -rn 'paulshaclaw' paulsha_cortex/monitor tests/test_stage9_*.py || echo CLEAN
```

Expected: `CLEAN`（若測試/檔案含 `PAULSHACLAW_CONFIG` env 名或 `paulshaclaw.yaml` 檔名字串——**保留不動**，那是外部契約字面值，非 import；Task 6 處理）

- [ ] **Step 2: 確認 PyYAML 依賴宣告**

monitor `config.py` `import yaml`。檢查 pyproject：

```bash
grep -n 'yaml\|dependencies' pyproject.toml
```

若 `dependencies = []` 未含 PyYAML：加入 `dependencies = ["PyYAML>=6"]`。（PyYAML 是通用第三方非 paulsha 產品，不違反「零 hippo 依賴」；A′ 指的是零 **paulsha-hippo** 依賴。）於 pyproject 加：

```toml
dependencies = ["PyYAML>=6"]
```

- [ ] **Step 3: 跑 monitor 測試確認綠**

Run: `python -m pip install -e . -q && python -m pytest tests/test_stage9_project_monitor.py tests/test_stage9_project_monitor_service.py -q`
Expected: 全 PASS

- [ ] **Step 4: Commit**

```bash
git add paulsha_cortex/monitor tests/test_stage9_*.py pyproject.toml
git commit -m "feat: 平移 monitor 套件 + 測試（配置沿舊 paulshaclaw.yaml；PyYAML 依賴）"
```

---

### Task 5: cortex CLI 接 deck / monitor 子命令

**Files:**
- Modify: `paulsha_cortex/cli.py`
- Test: `tests/test_cli_entry.py`（Plan 1 既有，追加）

**Interfaces:**
- Consumes: `paulsha_cortex.deck.cli:main(argv)`、`paulsha_cortex.monitor.__main__:main(argv)`
- Produces: `cortex deck …`、`cortex monitor …` 路由（psc shim 亦透傳至此）

- [ ] **Step 1: 追加失敗測試**

```python
# tests/test_cli_entry.py 追加
def test_routes_deck(monkeypatch):
    seen = {}
    def fake(argv=None):
        seen["argv"] = list(argv or [])
        return 0
    monkeypatch.setattr("paulsha_cortex.deck.cli.main", fake)
    assert main(["deck", "verify", "--change", "x"]) == 0
    assert seen["argv"] == ["verify", "--change", "x"]


def test_routes_monitor(monkeypatch):
    seen = {}
    def fake(argv=None):
        seen["argv"] = list(argv or [])
        return 0
    monkeypatch.setattr("paulsha_cortex.monitor.__main__.main", fake)
    assert main(["monitor", "--once"]) == 0
    assert seen["argv"] == ["--once"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_cli_entry.py -k "deck or monitor" -v`
Expected: FAIL（`monitor`/`deck` 目前落到 coordinator 透傳）

- [ ] **Step 3: cli.py 加路由**

在 `paulsha_cortex/cli.py` 的 `relay-hook` 分支之後、coordinator 透傳之前插入：

```python
    if args[0] == "deck":
        from paulsha_cortex.deck.cli import main as deck_main

        return int(deck_main(args[1:]) or 0)
    if args[0] == "monitor":
        from paulsha_cortex.monitor.__main__ import main as monitor_main

        return int(monitor_main(args[1:]) or 0)
```

並更新 `_USAGE`：

```python
_USAGE = "usage: cortex {install service|relay-hook|deck|monitor|<coordinator subcommand>} <args...>\n"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_cli_entry.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulsha_cortex/cli.py tests/test_cli_entry.py
git commit -m "feat: cortex CLI 接 deck/monitor 子命令路由"
```

---

### Task 6: monitor 配置改名 + base dir + legacy 讀取順序

**Files:**
- Modify: `paulsha_cortex/monitor/config.py`
- Test: `tests/test_monitor_config_resolution.py`（新增）

**Interfaces:**
- Consumes: `paths.project_config_root()`（Task 2）
- Produces: `_resolve_config_source(config_path)` 依 R1.6 讀取順序回傳 manual 來源路徑或 `None`（供 Task 7 判「兩來源皆缺」）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_monitor_config_resolution.py
from pathlib import Path
import pytest
from paulsha_cortex.monitor.config import _resolve_config_source


def _write(p: Path, text="workspaces:\n  - {name: a, path: /tmp/a}\n"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_prefers_new_project_cortex_over_legacy(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_MONITOR_CONFIG", raising=False)
    monkeypatch.delenv("PAULSHACLAW_CONFIG", raising=False)
    monkeypatch.setenv("PSC_PROJECT_CONFIG_ROOT", str(tmp_path / "agents"))
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path / "legacy"))
    new = _write(tmp_path / "agents" / "project-cortex.yaml")
    _write(tmp_path / "legacy" / "paulshaclaw.yaml")
    assert _resolve_config_source(None) == new


def test_legacy_only_transition(monkeypatch, tmp_path, recwarn):
    monkeypatch.delenv("PSC_MONITOR_CONFIG", raising=False)
    monkeypatch.delenv("PAULSHACLAW_CONFIG", raising=False)
    monkeypatch.setenv("PSC_PROJECT_CONFIG_ROOT", str(tmp_path / "agents"))
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path / "legacy"))
    legacy = _write(tmp_path / "legacy" / "paulshaclaw.yaml")
    assert _resolve_config_source(None) == legacy
    assert any("deprecated" in str(w.message).lower() for w in recwarn.list)


def test_none_when_no_manual(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_MONITOR_CONFIG", raising=False)
    monkeypatch.delenv("PAULSHACLAW_CONFIG", raising=False)
    monkeypatch.setenv("PSC_PROJECT_CONFIG_ROOT", str(tmp_path / "agents"))
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path / "legacy"))
    assert _resolve_config_source(None) is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_monitor_config_resolution.py -v`
Expected: FAIL（現行 `_resolve_config_source` 讀 `paulshaclaw.yaml`、缺檔 raise 非回 None）

- [ ] **Step 3: 改 config.py 的來源解析**

替換 `default_config_path` 與 `_resolve_config_source`：

```python
import warnings

def _new_manual_path() -> Path:
    return paths.project_config_root() / "project-cortex.yaml"


def _legacy_manual_path() -> Path:
    return paths.config_path("paulshaclaw.yaml")


def _resolve_config_source(config_path: Path | None) -> Path | None:
    """R1.6 讀取順序：顯式 > PSC_MONITOR_CONFIG > PAULSHACLAW_CONFIG > 新 > legacy。
    皆不存在回 None（呼叫端決定 hippo-only 或 FAIL）。"""
    if config_path is not None:
        return Path(config_path)
    for env in ("PSC_MONITOR_CONFIG", "PAULSHACLAW_CONFIG"):
        raw = os.environ.get(env, "").strip()
        if raw:
            if env == "PAULSHACLAW_CONFIG":
                warnings.warn("PAULSHACLAW_CONFIG 已 deprecated，改用 project-cortex.yaml", stacklevel=2)
            return Path(raw).expanduser()
    new = _new_manual_path()
    if new.exists():
        return new
    legacy = _legacy_manual_path()
    if legacy.exists():
        warnings.warn(
            f"讀取 legacy monitor 設定 {legacy}，請遷移至 {new}", stacklevel=2
        )
        return legacy
    return None
```

（確認檔頭 `import os` 已存在；`ENV_CONFIG_VAR` 常數若被別處引用，保留為 `"PAULSHACLAW_CONFIG"`。）

- [ ] **Step 4: 跑測試確認通過 + 既有 monitor 測試不回歸**

Run: `python -m pytest tests/test_monitor_config_resolution.py tests/test_stage9_project_monitor.py -q`
Expected: 全 PASS（`load_config` 對 `None` 來源的處理於 Task 7 定案；本 Task 若既有測試因「缺檔回 None」失敗，於 Task 7 Step 3 一併收斂——暫時在該測試標 `@pytest.mark.xfail(reason="Task 7 merge")`）

- [ ] **Step 5: Commit**

```bash
git add paulsha_cortex/monitor/config.py tests/test_monitor_config_resolution.py
git commit -m "feat: monitor 配置改名 project-cortex.yaml + base dir + legacy 讀取順序"
```

---

### Task 7: monitor merge adapter（manual ⊍ hippo，realpath 去重）

**Files:**
- Create: `paulsha_cortex/monitor/registry.py`
- Modify: `paulsha_cortex/monitor/config.py`（`load_config` 併入 hippo）、`paulsha_cortex/monitor/scanner.py`（scan 用合併集）
- Test: `tests/test_monitor_registry_merge.py`（新增，對齊 openspec cortex-consumer 4 情境）

**Interfaces:**
- Consumes: `_resolve_config_source`（Task 6）、`paths.project_config_root()`
- Produces:
  - `registry.load_hippo_roots(path: Path | None = None) -> list[Path]`（讀 `project-hippo.yaml` 的 project roots，絕對路徑；缺檔回 `[]`）
  - `registry.merge_project_dirs(manual_dirs: list[Path], hippo_roots: list[Path]) -> list[Path]`（union，依 `Path.resolve()` 去重、保序、manual 優先）
  - **`MonitorConfig` 新增欄位 `project_dirs: tuple[Path, ...] = ()`**（hippo roots）——`load_config` **簽名不變**（仍回 `MonitorConfig`），只多填此欄，**不打斷 Task 4 平移測試與既有 caller**
  - `scanner.scan_workspaces(config)`（讀 `config.workspaces`（walk）+ `config.project_dirs`（明確），合併去重後每個 project dir 產 `ProjectState`）

- [ ] **Step 1: 寫失敗測試（4 驗收情境）**

```python
# tests/test_monitor_registry_merge.py
from pathlib import Path
import pytest
from paulsha_cortex.monitor import registry
from paulsha_cortex.monitor.config import load_config


def test_merge_dedupes_by_realpath(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    merged = registry.merge_project_dirs([p], [p])  # 同 path 出現兩份
    assert merged == [p.resolve()]                   # 只算一個


def test_merge_union_order_manual_first(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert registry.merge_project_dirs([a], [b]) == [a.resolve(), b.resolve()]


def test_load_hippo_roots_missing_returns_empty(tmp_path):
    assert registry.load_hippo_roots(tmp_path / "nope.yaml") == []


def test_load_config_missing_hippo_graceful(monkeypatch, tmp_path):
    # manual 在、hippo 缺 → manual-only（project_dirs 空），不報錯
    monkeypatch.delenv("PSC_MONITOR_CONFIG", raising=False)
    monkeypatch.delenv("PAULSHACLAW_CONFIG", raising=False)
    monkeypatch.setenv("PSC_PROJECT_CONFIG_ROOT", str(tmp_path))
    (tmp_path / "project-cortex.yaml").write_text(
        f"workspaces:\n  - {{name: a, path: {tmp_path}}}\n", encoding="utf-8"
    )
    cfg = load_config()                # 簽名不變，回 MonitorConfig
    assert cfg.project_dirs == ()


def test_load_config_both_missing_fails(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_MONITOR_CONFIG", raising=False)
    monkeypatch.delenv("PAULSHACLAW_CONFIG", raising=False)
    monkeypatch.setenv("PSC_PROJECT_CONFIG_ROOT", str(tmp_path / "agents"))
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path / "legacy"))
    with pytest.raises(FileNotFoundError, match="無 project 設定"):
        load_config()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_monitor_registry_merge.py -v`
Expected: FAIL（`registry` 不存在、`load_config` 未回 tuple）

- [ ] **Step 3: 實作 registry + 併入 load_config/scan**

`paulsha_cortex/monitor/registry.py`：

```python
"""monitor 監控集 = manual project-cortex.yaml ⊍ hippo project-hippo.yaml。
讀共享檔為檔案契約，不 import paulsha_hippo（零依賴）。"""
from __future__ import annotations

from pathlib import Path

import yaml

from paulsha_cortex.config import paths


def _default_hippo_path() -> Path:
    return paths.project_config_root() / "project-hippo.yaml"


def load_hippo_roots(path: Path | None = None) -> list[Path]:
    """讀 project-hippo.yaml 的 project roots（絕對路徑）。缺檔回 []。
    schema：projects: [ {slug, roots: [..]} ]（hippo 產生端 paulsha-hippo#14）。"""
    src = path or _default_hippo_path()
    if not src.exists():
        return []
    data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    roots: list[Path] = []
    for project in data.get("projects", []) or []:
        for root in project.get("roots", []) or []:
            roots.append(Path(str(root)).expanduser())
    return roots


def merge_project_dirs(manual_dirs: list[Path], hippo_roots: list[Path]) -> list[Path]:
    """union；依 realpath 去重、保序、manual 優先。"""
    seen: set[Path] = set()
    out: list[Path] = []
    for candidate in [*manual_dirs, *hippo_roots]:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out
```

`config.py`：`MonitorConfig` 加 `project_dirs` 欄位；`load_config` **簽名不變**，多填 `project_dirs`、兩來源皆缺時 FAIL：

```python
@dataclass(frozen=True)
class MonitorConfig:
    workspaces: tuple[WorkspaceConfig, ...] = ()
    socket_path: Path = field(default_factory=default_socket_path)
    project_dirs: tuple[Path, ...] = ()    # hippo project-hippo.yaml roots


def load_config(*, config_path: Path | None = None) -> MonitorConfig:
    from paulsha_cortex.monitor import registry

    source = _resolve_config_source(config_path)
    hippo_roots = tuple(registry.load_hippo_roots())
    if source is None:
        if not hippo_roots:
            raise FileNotFoundError(
                "無 project 設定：manual（project-cortex.yaml / legacy）與 project-hippo.yaml 皆不存在"
            )
        return MonitorConfig(workspaces=(), project_dirs=hippo_roots)   # hippo-only
    text = Path(source).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text) or {}
    monitor = parsed.get("monitor", parsed)     # 沿用既有 schema：workspaces + optional socket_path
    workspaces = _parse_workspaces(monitor.get("workspaces"))
    socket_raw = monitor.get("socket_path")
    socket_path = Path(str(socket_raw)).expanduser() if socket_raw else default_socket_path()
    return MonitorConfig(workspaces=workspaces, socket_path=socket_path, project_dirs=hippo_roots)
```

（`_parse_workspaces` / socket 解析沿用 Task 4 平移進來的既有實作，僅把回傳包成含 `project_dirs` 的 `MonitorConfig`。）

`scanner.py` 的 `scan_workspaces(config)` **簽名不變**，改為讀 `config.workspaces`（walk）+ `config.project_dirs`（明確）合併：

```python
def scan_workspaces(config) -> tuple[ProjectState, ...]:
    from paulsha_cortex.monitor.registry import merge_project_dirs

    manual_dirs: list[Path] = []
    for workspace in config.workspaces:
        manual_dirs.extend(_list_project_dirs(workspace.path, _IGNORE_DIRS))
    states = []
    for project_dir in merge_project_dirs(manual_dirs, list(config.project_dirs)):
        state = _project_state(project_dir)   # 沿用既有「由 dir 產 ProjectState」邏輯
        if state is not None:
            states.append(state)
    return tuple(states)
```

（`_IGNORE_DIRS` 與 `_project_state` 對齊 Task 4 平移進來的 scanner 內既有 ignore 常數與 per-dir 推導函式——**動工前先讀 `paulsha_cortex/monitor/scanner.py` 確認實名**，勿發明；此處僅示意合併點。）

呼叫端 `__main__`（`--once`）與 `ProjectMonitorService`：`load_config` 簽名不變，故**無需改動**；`scan_workspaces(config)` 簽名不變亦無需改。

- [ ] **Step 4: 跑測試確認通過 + 解除 Task 6 xfail + 全 monitor 測試綠**

Run: `python -m pytest tests/test_monitor_registry_merge.py tests/test_monitor_config_resolution.py tests/test_stage9_project_monitor.py tests/test_stage9_project_monitor_service.py -q`
Expected: 全 PASS（Task 6 若有 xfail 於此改回正常斷言）

- [ ] **Step 5: Commit**

```bash
git add paulsha_cortex/monitor/registry.py paulsha_cortex/monitor/config.py paulsha_cortex/monitor/scanner.py paulsha_cortex/monitor/__main__.py paulsha_cortex/monitor/service.py tests/test_monitor_registry_merge.py tests/test_monitor_config_resolution.py
git commit -m "feat: monitor merge adapter（manual ⊍ hippo，realpath 去重，缺檔契約）"
```

---

### Task 8: monitor 併入 install service（一次裝 manager + monitor）

**Files:**
- Create: `paulsha_cortex/deploy/templates/monitor.service.tmpl`
- Modify: `paulsha_cortex/deploy/installer.py`
- Test: `tests/test_install_service.py`（Plan 1 既有，追加）

**Interfaces:**
- Consumes: Task 5 的 `cortex monitor` 入口
- Produces: `install_service` 除 manager 外亦 render+install `<instance>-monitor.service`（monitor 為 serve、single-instance 靠 socket 佔用檢查、無 timer）

- [ ] **Step 1: 追加失敗測試**

```python
# tests/test_install_service.py 追加
def test_install_service_installs_monitor_unit(tmp_path, monkeypatch):
    from paulsha_cortex.deploy import installer
    monkeypatch.setattr(installer, "_systemctl_available", lambda: False)
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "repo"; repo.mkdir()
    import subprocess
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert installer.main(["service", "--repo-root", str(repo)]) == 0
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    assert (unit_dir / "cortex-manager.service").exists()
    assert (unit_dir / "cortex-monitor.service").exists()
    monitor_unit = (unit_dir / "cortex-monitor.service").read_text()
    assert "cortex monitor" in monitor_unit or "paulsha_cortex.monitor" in monitor_unit
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_install_service.py -k monitor -v`
Expected: FAIL（`cortex-monitor.service` 不存在）

- [ ] **Step 3: monitor 模板 + installer 併裝**

`paulsha_cortex/deploy/templates/monitor.service.tmpl`：

```ini
[Unit]
Description=__INSTANCE__ project monitor service (paulsha-cortex)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
EnvironmentFile=-%h/.agents/core/runtime/__INSTANCE__-manager.env
ExecStart=__PY__ -m paulsha_cortex.monitor
KillMode=control-group
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

`installer.py`：`render_units` 增 monitor 單元；`install_service` 亦寫 monitor.service 並 enable（monitor 無 timer、直接 enable service）：

```python
def render_units(instance: str, interval: int) -> dict[str, str]:
    # ...既有 manager service/timer...
    monitor = _template("monitor.service.tmpl").replace("__INSTANCE__", instance)
    monitor = monitor.replace("__PY__", sys.executable)
    units[f"{instance}-monitor.service"] = monitor
    return units
```

`install_service` 內 enable 段加：

```python
    subprocess.run(["systemctl", "--user", "enable", f"{instance}-monitor.service"], check=True)
```

（`_write_managed_env` 的 `PY`/`PSC_REPO_ROOT` monitor 亦讀同一 env file；monitor 不需 repo_root 但共用無害。）

- [ ] **Step 4: 跑測試確認通過 + fresh-install 冒煙**

Run: `python -m pytest tests/test_install_service.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulsha_cortex/deploy tests/test_install_service.py
git commit -m "feat: install service 併裝 monitor unit（一次裝 manager+monitor）"
```

---

### Task 9: persona↔deck 同包 import + persona 重定義實查

**Files:**
- Modify: `paulsha_cortex/persona/loader.py`
- Modify: `docs/`（persona 概念澄清，見 Step 3）

**Interfaces:**
- Produces: persona loader 對 deck 為同包正常 import（不再 fail-open lazy）；docs 澄清 AgentInstance/Persona/Guardrail/Manager

- [ ] **Step 1: 實查 persona 有無 code 把 contract 與 enforcement 混在一起**

```bash
grep -rn 'class Persona\|enforce\|guardrail\|GuardrailDecision' paulsha_cortex/persona/contract.py paulsha_cortex/persona/guardrail.py | head
```

Expected: `contract.py` 僅 `PersonaContract`（資料）、`guardrail.py` 僅 `PersonaGuardrail`/`GuardrailDecision`（enforcement）——**確認分離**。若發現 contract.py 內含 enforce 邏輯，記錄於 `docs/review.md`（不在本 Task 重構，僅回報 orchestrator）。

- [ ] **Step 2: loader deck import 改同包正常 import**

`paulsha_cortex/persona/loader.py`：`from paulshaclaw.deck.schema import ...`（Task 3 sed 已改成 `paulsha_cortex.deck.schema`）確認為模組頂層或函式內 import 皆可；deck 同包必存在，**移除 fail-open 的 `except ImportError: return`**（deck 缺席不再是有效情境）。改為：

```python
from paulsha_cortex.deck.schema import DeckSchemaError, DEFAULT_CARDS_PATH, load_cards
```

於頂層；`_warn_unknown_skills` 內移除 `try/except ImportError`（保留對 `DeckSchemaError` 的 warning 處理）。

- [ ] **Step 3: docs 澄清 persona 概念**

`README.md` 或 `docs/persona.md` 補一段（zh-tw）：
> persona = manager 與 guardrail 共同引用的角色契約資料（role profile + scope subject）；不是執行者（AgentInstance = 實際跑的 runtime session）、不是安全管理者（guardrail/policy engine 讀 persona 契約做 enforcement）。

- [ ] **Step 4: 跑 persona 全測試確認不回歸**

Run: `python -m pytest tests/ -k persona -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add paulsha_cortex/persona/loader.py README.md docs/
git commit -m "refactor: persona↔deck 同包正常 import；docs 澄清 persona 為角色契約資料"
```

---

### Task 10: 去識別化 + 零依賴 + 全測試 + README

**Files:**
- Modify: `README.md`（deck/monitor 章節）、`pyproject.toml`（package-data if needed）

**Interfaces:**
- Produces: 可 push 的乾淨分支

- [ ] **Step 1: 去識別化掃描**

```bash
cd ~/prj_pri/paulsha-cortex
grep -rnE '/home/paul_chen|paul_chen' --include='*.py' --include='*.md' --include='*.yaml' --include='*.yml' --include='*.tmpl' paulsha_cortex tests docs && echo 'FOUND—需清' || echo CLEAN
```

Expected: `CLEAN`（命中即改 `$HOME`/`tmp_path`/佔位符後重掃）

- [ ] **Step 2: 零依賴驗證（無 hippo runtime import；deps 僅 PyYAML）**

```bash
grep -rn 'paulsha_hippo' paulsha_cortex/ | grep -v test | wc -l   # 期望 0
grep -n -A2 'dependencies' pyproject.toml                          # 僅 PyYAML
```

Expected: hippo import = `0`；dependencies 僅 `PyYAML>=6`

- [ ] **Step 3: package-data 涵蓋 monitor 模板 + 全測試**

確認 `[tool.setuptools.package-data]` 的 `"paulsha_cortex.deploy" = ["templates/*.tmpl"]` 已涵蓋 `monitor.service.tmpl`（同目錄，glob 命中）。

Run: `python -m pip install -e . -q && python -m pytest tests/ -q`
Expected: 全 PASS（Plan 1 的 277 + deck/monitor/registry/config 新增）

- [ ] **Step 4: README 補 deck/monitor**

`README.md` 補 `cortex deck compile …`、`cortex monitor --once` / serve、registry merge（`project-cortex.yaml` ⊍ `project-hippo.yaml`）、`install service` 一次裝 manager+monitor。zh-tw。

- [ ] **Step 5: Commit**

```bash
git add README.md pyproject.toml
git commit -m "docs: README 補 deck/monitor + registry；去識別化/零依賴驗證"
```

---

### Task 11: fresh-install E2E + push + PR（不 merge）

**Files:**
- （無 code；驗證 + 發佈）

**Interfaces:**
- Produces: 遠端 PR + merge 後 main 的**新 pin SHA**（Plan 2 以此取代 `2e67100`）

- [ ] **Step 1: fresh-install E2E（source tree 外驗證）**

```bash
rm -rf /tmp/c1b && python -m venv /tmp/c1b && /tmp/c1b/bin/pip install ~/prj_pri/paulsha-cortex -q
cd /tmp && /tmp/c1b/bin/cortex deck --help >/dev/null; echo "deck exit=$?"
/tmp/c1b/bin/cortex monitor --once >/dev/null 2>&1; echo "monitor once exit=$?"
/tmp/c1b/bin/pip show paulsha-cortex | grep -i requires
```

Expected: deck/monitor 入口可跑（monitor --once 在無 config 時 exit 1 並印「無 project 設定」屬預期）；`Requires:` 僅 PyYAML（無 paulsha-hippo）

- [ ] **Step 2: push + 開 PR**

```bash
cd ~/prj_pri/paulsha-cortex && git push -u origin feature/plan1b-deck-monitor
gh pr create --fill --label policy-exempt:issue-link --label skip-changelog
```

PR body 引用 `hamanpaul/paulshaclaw#232`。**不 merge**——orchestrator 跑 codex 對抗審查後當 merge gate。

- [ ] **Step 3: 記錄新 pin SHA（merge 後由 orchestrator 執行）**

merge 後 `git checkout main && git pull --ff-only && git rev-parse HEAD` → 填入主 repo openspec `tasks.md` 1b.9，取代 `2e67100`；Plan 2 以此 pin。

- [ ] **Step 4: 清理來源 worktree**

```bash
git -C /home/paul_chen/prj_pri/paulshaclaw worktree remove /tmp/claw-src
```
