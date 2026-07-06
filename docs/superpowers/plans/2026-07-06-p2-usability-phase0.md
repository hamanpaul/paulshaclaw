# P2 易用性 Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **實作者：gpt5.3-codex**。兩個 Task 群組＝兩個 PR：PR-A（`feature/125-psc-entry-version`）無依賴可先行；PR-B（`feature/91-env-facade`）**依賴 P0-1 Stage A 的 env 化先 merge**。各自 worktree。測試：`python3 -m pytest tests/ paulshaclaw/memory/tests/ -q`。

**Goal:** `psc` 單一入口＋版號治理復活（PR-A）；env facade 消滅散落 `Path.home()` 與硬編碼路徑（PR-B，#91）。

**Architecture:** PR-A＝薄 dispatcher（零行為變更）＋pytest 版號一致性；PR-B＝`paulshaclaw/config/paths.py`（stdlib-only facade，env→契約預設），29 處呼叫點機械遷移＋grep-zero 驗收。

**Tech Stack:** Python 3.10+、setuptools `[project.scripts]`、pytest。

**依據**：`openspec/changes/p2-usability-phase0/`＋`docs/superpowers/specs/2026-07-06-p2-usability-phase0-design.md`＋#91、#125。

---

### Task 1（PR-A）: psc 傘狀入口

**Files:**
- Create: `paulshaclaw/cli.py`
- Modify: `pyproject.toml`（`[project]` 區塊後加 `[project.scripts]`）
- Test: `tests/test_psc_cli.py`（新檔）

- [ ] **Step 1: 寫失敗測試**

```python
from paulshaclaw import cli

def test_route_memory(monkeypatch):
    called = {}
    monkeypatch.setattr("paulshaclaw.memory.cli.main", lambda argv: called.setdefault("argv", argv) or 0)
    rc = cli.main(["memory", "dream", "status"])
    assert rc == 0 and called["argv"] == ["memory", "dream", "status"]

def test_route_coordinator(monkeypatch):
    monkeypatch.setattr("paulshaclaw.coordinator.cli.main", lambda argv: 0)
    assert cli.main(["coordinator", "jobs"]) == 0

def test_unknown_subcommand_exit_2(capsys):
    assert cli.main(["nosuch"]) == 2
    assert "usage" in capsys.readouterr().err.lower()

def test_no_args_exit_2():
    assert cli.main([]) == 2
```

- [ ] **Step 2: RED** — `python3 -m pytest tests/test_psc_cli.py -v`（模組不存在 → ImportError FAIL）
- [ ] **Step 3: 實作 `paulshaclaw/cli.py`**

```python
"""psc 傘狀入口——薄 dispatcher，零行為變更（#125 Phase 0）。"""
from __future__ import annotations

import sys
from typing import Sequence

_USAGE = "usage: psc {memory|coordinator} <args...>\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(_USAGE)
        return 2
    head, rest = args[0], args[1:]
    if head == "memory":
        from paulshaclaw.memory.cli import main as memory_main
        return int(memory_main(["memory", *rest]) or 0)   # memory.cli 首參即 'memory'（cli.py:24 慣例）
    if head == "coordinator":
        from paulshaclaw.coordinator.cli import main as coordinator_main
        return int(coordinator_main(rest) or 0)
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

  `pyproject.toml` 加：

```toml
[project.scripts]
psc = "paulshaclaw.cli:main"
```

- [ ] **Step 4: GREEN**＋實測：`pip install -e . --quiet && psc memory dream status --memory-root /tmp/nonexist; echo $?`（預期跑到 memory CLI 的錯誤處理，非 ImportError）。**注意**：`test_route_memory` 若實際 memory.cli `main(["memory","dream","status"])` 參數形狀不符，以 `paulshaclaw/memory/cli.py:24` 實況修 dispatcher，不改 memory.cli。
- [ ] **Step 5: Commit** — `feat(cli): psc 傘狀入口（#125 Phase 0）`

### Task 2（PR-A）: 版號一致性＋清殼

**Files:**
- Modify: `VERSION`（`0.0.0`→`0.1.0`）
- Delete: `paulshaclaw/janitor/`、`paulshaclaw/chat/`（0 LOC 空殼；**保留 `paulshaclaw/config/`**）
- Test: `tests/test_version_consistency.py`（新檔）

- [ ] **Step 1: 失敗測試**

```python
import re, tomllib
from pathlib import Path

def test_version_file_matches_pyproject():
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION").read_text().strip()
    py = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert version == py

def test_latest_version_tag_matches_if_any():
    import subprocess
    root = Path(__file__).resolve().parents[1]
    tags = subprocess.run(["git", "tag", "--list", "v*"], capture_output=True, text=True, cwd=root).stdout.split()
    if not tags:
        return  # tag 由 owner 打；打了之後本測試開始把關
    latest = sorted(tags, key=lambda t: [int(x) for x in re.sub(r"^v", "", t).split(".")])[-1]
    assert re.sub(r"^v", "", latest) == (root / "VERSION").read_text().strip()  # R-07 正規化比對
```

- [ ] **Step 2: RED**（VERSION=0.0.0 ≠ 0.1.0）→ **Step 3**: `VERSION` 改 `0.1.0`；`git rm -r paulshaclaw/janitor paulshaclaw/chat`（先 `rg -n "janitor|chat" paulshaclaw --include='*.py' -l` 確認無 import 者——core/daemon 等如有引用先跟隨移除 import）。
- [ ] **Step 4: GREEN＋全回歸** → **Step 5: Commit** — `chore(version): VERSION 對齊 0.1.0＋版號一致性測試＋移除空殼包`。tag `v0.1.0` **由 owner 打**（或明確授權後代行；R-07 禁非版本 tag）。

### Task 3（PR-B）: env facade（#91）

**Files:**
- Create: `paulshaclaw/config/__init__.py`（若缺）、`paulshaclaw/config/paths.py`
- Test: `tests/test_config_paths.py`（新檔）

- [ ] **Step 1: 失敗測試**

```python
from pathlib import Path
from paulshaclaw.config import paths

def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(tmp_path / "m"))
    assert paths.memory_root() == tmp_path / "m"

def test_default_contract(monkeypatch, tmp_path):
    for k in ("PSC_MEMORY_ROOT", "PSC_AGENTS_ROOT", "PSC_CONFIG_ROOT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.memory_root() == tmp_path / ".agents" / "memory"
    assert paths.agents_root() == tmp_path / ".agents"
    assert paths.config_root() == tmp_path / ".config" / "paulshaclaw"
```

- [ ] **Step 2: RED → Step 3: 實作 `paths.py`**

```python
"""路徑 facade——唯一 Path.home() 推導點（#91；path-split 契約不變）。stdlib-only，禁 import 業務包。"""
from __future__ import annotations

import os
from pathlib import Path


def _root(env: str, default: Path) -> Path:
    value = os.environ.get(env, "").strip()
    return Path(value).expanduser() if value else default


def agents_root() -> Path:
    return _root("PSC_AGENTS_ROOT", Path.home() / ".agents")


def memory_root() -> Path:
    return _root("PSC_MEMORY_ROOT", agents_root() / "memory")


def config_root() -> Path:
    return _root("PSC_CONFIG_ROOT", Path.home() / ".config" / "paulshaclaw")


def repo_root() -> Path:
    return _root("PSC_REPO_ROOT", Path(__file__).resolve().parents[2])


def worktree_root() -> Path:
    return _root("PSC_WORKTREE_ROOT", repo_root().parent / f"{repo_root().name}-worktrees")


def extra_corpus_root() -> Path | None:
    value = os.environ.get("PSC_EXTRA_CORPUS_ROOT", "").strip()  # 收編 P0-1 Stage A 過渡 env（別名保留一版）
    return Path(value).expanduser() if value else None
```

- [ ] **Step 4: GREEN → Commit** — `feat(config): env facade paths.py（#91）`

### Task 4（PR-B）: 呼叫點遷移＋grep-zero

**Files:**
- Modify: `rg -n "Path.home()" paulshaclaw --include='*.py' -g '!*/tests/*'` 全部命中（≈29 處）＋ `paulshaclaw/coordinator/seams.py:55-56`、`paulshaclaw/memory/importer/backfill.py:72` 硬編碼預設
- Test: 既有全套件（假 `$HOME` 由 facade 測試涵蓋）

- [ ] **Step 1: 逐檔機械遷移**——規則：`Path.home() / ".agents" / "memory"` → `paths.memory_root()`；`Path.home() / ".agents"` → `paths.agents_root()`；`Path.home() / ".config" / "paulshaclaw"` → `paths.config_root()`；seams.py/backfill.py 的 `/home/...` 字面預設 → 對應 facade 函式。import 一律 `from paulshaclaw.config import paths`。**不改行為、不順手重構**；hooks 目錄下檔案同規則（部署面見 Step 4）。
- [ ] **Step 2: grep-zero 驗收**

Run: `rg -n "Path\.home\(\)" paulshaclaw --include='*.py' -g '!*/tests/*' -g '!*config/paths.py*'; rg -n "/home/" paulshaclaw scripts --include='*.py' -g '!*/tests/*'`
Expected: 兩者皆 0 命中。

- [ ] **Step 3: 全回歸 GREEN**（`python3 -m pytest tests/ paulshaclaw/memory/tests/ -q`）
- [ ] **Step 4: LLM 讀點收斂＋部署**：upstream URL／agent_exec 相關 `os.environ` 散讀集中到 config 層讀點並補文件（`docs/`：config 鍵、env 覆寫鏈、後端替換步驟）；hooks 檔有動 → `install.sh --skip-venv` 重部署＋import 健檢（複製坑）。
- [ ] **Step 5: Commit** — `refactor(paths): 29 處 Path.home() 遷移 facade＋硬編碼預設清除（Closes #91）`

---

**Self-review**：spec 2 capability ↔ Task 1（psc-cli-entry：路由/exit 2/版號測試）、Task 3/4（env-path-facade：env 覆寫/契約預設/唯一 home 點）；PR-B 依賴 P0-1 Stage A 已在 header 載明；無 TBD。
