# paulsha-conventions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本地建出 `paulsha-conventions` 專案的完整實作：policy-check 引擎（16 條規則）、測試（每條規則 fixture）、composite action、reusable workflow 與三支 helper script；自身通過自己的 policy-check（self dog-food）。不含 GitHub repo 建立與 release（留給 spec-1 Plan 2）。

**Architecture:** Python 3.11+ 寫 rule logic（每條規則獨立 module，遵循 `Rule` protocol），pytest 參數化跑 fixture。GitHub composite action 呼叫 `python -m policy_check`。Reusable workflow 包一層 `workflow_call` 給下游 repo 用。所有 rules 回傳統一 `RuleResult(rule_id, status, message, diff?)`，由 `report.py` 彙整成 GitHub step summary + exit code。

**Tech Stack:** Python 3.11+, PyYAML, pytest, Bash, GitHub Actions (composite action + reusable workflow), gh CLI.

**Reference spec:** `docs/superpowers/specs/2026-04-21-hamanpaul-project-policy-design.md`

**Working directory:** `~/prj_pri/paulsha-conventions/`（本 plan 全程在此）。paulshaclaw repo 只持有 plan 文件本身；實作產物在新的本地 repo。

## Execution Snapshot（2026-04-22）

本 plan 對應的 **local baseline implementation** 已在
`~/prj_pri/paulsha-conventions` 落地完成，實作 branch 為
`feature/policy-rules-foundation`。

### 已完成成果

- R-01 ~ R-16 規則、fixtures、pytest 測試
- `policy_check` CLI / report / config / PR context / registry
- reusable workflow、composite action、self-test wiring
- `scripts/update-cli-help.sh`、`apply-branch-protection.sh`、`worktree-cleanup.sh`
- self dog-food：README / CHANGELOG / agent files / `.paul-project.yml`
- zh-TW 使用者文件與 agent convention files

### 最終驗證結果

- `pytest -q`：通過
- `python -m policy_check --repo .`：16 rules 全綠
- external repo 變更已完成 spec review 與 code review gate

### 目前刻意保留的狀態

- `VERSION` 仍為 `0.0.0`：表示尚未 release、尚未 tag、仍在 feature branch
- `policy_version` 為 `1.0.0`：表示本 repo 目前遵循的 policy 規範版本
- push / PR / merge / release 不在本 plan 本輪實作範圍內

### 待後續處理

- 將 branch push 到 upstream 並建立 PR
- merge 後依 release 策略更新 `VERSION` / CHANGELOG / tag
- 依 spec-1 的 3-repo 架構，把成果擴散到 `hamanpaul/.github` 與 `paul-project-template`

---

## Task 1: 建立本地 repo 骨架

**Files:**
- Create: `~/prj_pri/paulsha-conventions/.git/` (via `git init`)
- Create: `~/prj_pri/paulsha-conventions/pyproject.toml`
- Create: `~/prj_pri/paulsha-conventions/.gitignore`
- Create: `~/prj_pri/paulsha-conventions/policy_check/__init__.py`
- Create: `~/prj_pri/paulsha-conventions/tests/__init__.py`
- Create: `~/prj_pri/paulsha-conventions/VERSION`

- [ ] **Step 1: 建目錄並 init git**

```bash
mkdir -p ~/prj_pri/paulsha-conventions
cd ~/prj_pri/paulsha-conventions
git init -b main
```

- [ ] **Step 2: 寫 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "policy-check"
version = "0.0.0"
description = "Cross-repo policy checker for hamanpaul/*"
requires-python = ">=3.11"
dependencies = [
    "PyYAML>=6.0",
]

[project.optional-dependencies]
test = ["pytest>=7.0"]

[project.scripts]
policy-check = "policy_check.cli:main"

[tool.setuptools.packages.find]
include = ["policy_check*"]
```

- [ ] **Step 3: 寫 .gitignore**

```
__pycache__/
*.pyc
*.egg-info/
.venv/
.pytest_cache/
dist/
build/
```

- [ ] **Step 4: 建立空 package markers 與 VERSION**

```bash
mkdir -p policy_check/rules tests/fixtures
touch policy_check/__init__.py policy_check/rules/__init__.py tests/__init__.py
echo "0.0.0" > VERSION
```

- [ ] **Step 5: 建 venv 並 editable install**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

- [ ] **Step 6: 初始 commit**

```bash
git add .
git commit -m "chore: initialize paulsha-conventions skeleton"
```

---

## Task 2: Rule 基礎建設（protocol / result / registry）

**Files:**
- Create: `policy_check/rules/base.py`
- Create: `policy_check/report.py`
- Create: `policy_check/config.py`

- [ ] **Step 1: 寫 base.py（Rule protocol + Result）**

```python
# policy_check/rules/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, Optional


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"       # 豁免 label 生效
    WARN = "warn"       # 未來 MINOR 新 rule 的過渡期


@dataclass
class RuleResult:
    rule_id: str
    status: Status
    message: str
    detail: str = ""      # 供 report 展開（例 diff）
    exempt_label: Optional[str] = None


@dataclass
class RuleContext:
    repo_root: Path
    profile: str                          # stage-driven | flat
    policy_version: str
    config: dict = field(default_factory=dict)     # 解析後的 .paul-project.yml
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None
    pr_labels: list[str] = field(default_factory=list)
    pr_base_ref: Optional[str] = None              # e.g. main
    pr_head_ref: Optional[str] = None              # e.g. feature/foo
    changed_files: list[str] = field(default_factory=list)
    latest_tag: Optional[str] = None


class Rule(Protocol):
    rule_id: str                                   # 例 "R-01"
    exempt_label: Optional[str]                    # 例 "policy-exempt:readme-sections" 或 None

    def check(self, ctx: RuleContext) -> RuleResult: ...
```

- [ ] **Step 2: 寫 config.py（載 `.paul-project.yml`）**

```python
# policy_check/config.py
from pathlib import Path
import yaml


REQUIRED_KEYS = {"policy_profile", "policy_version"}
VALID_PROFILES = {"stage-driven", "flat"}
DEFAULT_CODE_PATHS = {
    "stage-driven": ["**/*.py", "**/*.sh", "scripts/**"],
    "flat":         ["**/*.py", "**/*.sh", "scripts/**"],
}


class ConfigError(Exception):
    pass


def load(repo_root: Path) -> dict:
    path = repo_root / ".paul-project.yml"
    if not path.exists():
        raise ConfigError(f".paul-project.yml not found at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ConfigError(f".paul-project.yml missing keys: {sorted(missing)}")
    if data["policy_profile"] not in VALID_PROFILES:
        raise ConfigError(
            f"policy_profile must be one of {VALID_PROFILES}, got {data['policy_profile']}"
        )
    data.setdefault("code_paths", DEFAULT_CODE_PATHS[data["policy_profile"]])
    data.setdefault("cli", [])
    return data
```

- [ ] **Step 3: 寫 report.py（彙整 + exit code）**

```python
# policy_check/report.py
import os
import sys
from typing import Iterable

from policy_check.rules.base import RuleResult, Status


def emit(results: Iterable[RuleResult]) -> int:
    results = list(results)
    lines = ["# Policy Check Report\n"]
    fails = [r for r in results if r.status == Status.FAIL]
    skips = [r for r in results if r.status == Status.SKIP]
    passes = [r for r in results if r.status == Status.PASS]

    lines.append(f"- pass: {len(passes)}")
    lines.append(f"- fail: {len(fails)}")
    lines.append(f"- skip (exempt): {len(skips)}\n")

    for r in sorted(results, key=lambda x: x.rule_id):
        icon = {"pass": ":white_check_mark:", "fail": ":x:", "skip": ":warning:", "warn": ":warning:"}[r.status.value]
        lines.append(f"## {icon} {r.rule_id} — {r.status.value}")
        lines.append(r.message)
        if r.exempt_label:
            lines.append(f"exempt via: `{r.exempt_label}`")
        if r.detail:
            lines.append(f"\n<details><summary>detail</summary>\n\n```\n{r.detail}\n```\n\n</details>")
        lines.append("")

    report = "\n".join(lines)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(report)
    else:
        print(report)

    return 1 if fails else 0
```

- [ ] **Step 4: Commit**

```bash
git add policy_check/rules/base.py policy_check/config.py policy_check/report.py
git commit -m "feat(core): add Rule protocol, RuleContext, report emitter, config loader"
```

---

## Task 3: CLI 入口與測試 harness

**Files:**
- Create: `policy_check/cli.py`
- Create: `policy_check/__main__.py`
- Create: `policy_check/pr_context.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 寫 pr_context.py（收集 PR/git 資訊）**

```python
# policy_check/pr_context.py
import json
import os
import subprocess
from pathlib import Path


def load_event_payload() -> dict:
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text())


def pr_meta_from_event(event: dict) -> dict:
    pr = event.get("pull_request") or {}
    return {
        "pr_title": pr.get("title"),
        "pr_body": pr.get("body"),
        "pr_labels": [l["name"] for l in pr.get("labels", [])],
        "pr_base_ref": (pr.get("base") or {}).get("ref"),
        "pr_head_ref": (pr.get("head") or {}).get("ref"),
    }


def changed_files(base_ref: str | None, repo_root: Path) -> list[str]:
    if not base_ref:
        return []
    cmd = ["git", "-C", str(repo_root), "diff", "--name-only", f"origin/{base_ref}...HEAD"]
    try:
        out = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def latest_tag(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "describe", "--tags", "--abbrev=0"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip() or None
    except subprocess.CalledProcessError:
        return None
```

- [ ] **Step 2: 寫 cli.py**

```python
# policy_check/cli.py
import argparse
import sys
from pathlib import Path

from policy_check import config as cfg
from policy_check import pr_context as prc
from policy_check.rules.base import RuleContext
from policy_check.rules import registry
from policy_check.report import emit


def build_context(args: argparse.Namespace) -> RuleContext:
    repo_root = Path(args.repo).resolve()
    conf = cfg.load(repo_root)
    event = prc.load_event_payload()
    pr_meta = prc.pr_meta_from_event(event)
    return RuleContext(
        repo_root=repo_root,
        profile=conf["policy_profile"],
        policy_version=conf["policy_version"],
        config=conf,
        pr_title=pr_meta.get("pr_title") or args.pr_title,
        pr_body=pr_meta.get("pr_body") or args.pr_body,
        pr_labels=pr_meta.get("pr_labels") or (args.pr_labels.split(",") if args.pr_labels else []),
        pr_base_ref=pr_meta.get("pr_base_ref") or args.pr_base_ref,
        pr_head_ref=pr_meta.get("pr_head_ref") or args.pr_head_ref,
        changed_files=prc.changed_files(pr_meta.get("pr_base_ref") or args.pr_base_ref, repo_root),
        latest_tag=prc.latest_tag(repo_root),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="policy-check")
    p.add_argument("--repo", default=".", help="Repository root")
    p.add_argument("--pr-title", default=None)
    p.add_argument("--pr-body", default=None)
    p.add_argument("--pr-labels", default=None, help="Comma-separated")
    p.add_argument("--pr-base-ref", default=None)
    p.add_argument("--pr-head-ref", default=None)
    p.add_argument("--only", default=None, help="Comma-separated rule IDs (e.g. R-01,R-09)")
    args = p.parse_args(argv)

    ctx = build_context(args)
    rules = registry.load_all()
    if args.only:
        wanted = set(args.only.split(","))
        rules = [r for r in rules if r.rule_id in wanted]
    results = [r.check(ctx) for r in rules]
    return emit(results)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 寫 __main__.py 與空 registry**

```python
# policy_check/__main__.py
from policy_check.cli import main
import sys
sys.exit(main())
```

```python
# policy_check/rules/__init__.py 改寫
from policy_check.rules import registry  # noqa
```

```python
# policy_check/rules/registry.py （新檔）
from importlib import import_module
from pkgutil import iter_modules
from policy_check.rules.base import Rule

_RULE_MODULES = []  # 由各 rule module 透過 register() 填入


def register(rule_cls):
    _RULE_MODULES.append(rule_cls)
    return rule_cls


def load_all() -> list[Rule]:
    # 確保所有 rule module 被 import（觸發 register decorator）
    import policy_check.rules as pkg
    for m in iter_modules(pkg.__path__):
        if m.name.startswith("r") and m.name[1:3].isdigit():
            import_module(f"policy_check.rules.{m.name}")
    return [cls() for cls in _RULE_MODULES]
```

- [ ] **Step 4: 寫 tests/conftest.py**

```python
# tests/conftest.py
import shutil
from pathlib import Path
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_repo(tmp_path):
    def _make(name: str) -> Path:
        src = FIXTURE_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"fixture {name} not found at {src}")
        dst = tmp_path / name
        shutil.copytree(src, dst)
        return dst
    return _make
```

- [ ] **Step 5: 驗證 CLI 可跑（即使沒 rule）**

先在空 repo 建最小 `.paul-project.yml`：

```bash
mkdir -p /tmp/pc-smoke && cd /tmp/pc-smoke
cat > .paul-project.yml <<EOF
policy_profile: flat
policy_version: 1.0.0
EOF
cd - && python -m policy_check --repo /tmp/pc-smoke
```

Expected: 輸出 "pass: 0 / fail: 0 / skip: 0"（因為還沒 rule），exit 0。

- [ ] **Step 6: Commit**

```bash
git add policy_check/cli.py policy_check/__main__.py policy_check/pr_context.py \
        policy_check/rules/__init__.py policy_check/rules/registry.py tests/conftest.py
git commit -m "feat(core): add CLI entry, PR context collection, rule registry, test harness"
```

---

## Task 4: R-01/R-03/R-05 — 檔案存在性規則

**Files:**
- Create: `policy_check/rules/r01_readme_exists.py`
- Create: `policy_check/rules/r03_changelog_exists.py`
- Create: `policy_check/rules/r05_version_exists.py`
- Create: `tests/fixtures/valid-minimal/`（包含 README.md / CHANGELOG.md / VERSION / .paul-project.yml）
- Create: `tests/fixtures/missing-readme/`（缺 README.md）
- Create: `tests/fixtures/missing-changelog/`（缺 CHANGELOG.md）
- Create: `tests/fixtures/missing-version/`（缺 VERSION）
- Create: `tests/test_rules.py`

- [ ] **Step 1: 建 valid-minimal fixture**

```bash
cd ~/prj_pri/paulsha-conventions
mkdir -p tests/fixtures/valid-minimal
cd tests/fixtures/valid-minimal

cat > .paul-project.yml <<EOF
policy_profile: flat
policy_version: 1.0.0
EOF

cat > README.md <<'EOF'
# Sample
More than 100 bytes of content to satisfy R-01 size floor.
This is fixture content for the policy checker tests.

## Install
placeholder

## Usage
placeholder

## Version
0.0.0
EOF

cat > CHANGELOG.md <<'EOF'
# Changelog

## [Unreleased]

### Added
- initial
EOF

echo "0.0.0" > VERSION
cd ~/prj_pri/paulsha-conventions
```

- [ ] **Step 2: 由 valid-minimal 拷出違規 fixtures**

```bash
cd tests/fixtures
cp -r valid-minimal missing-readme && rm missing-readme/README.md
cp -r valid-minimal missing-changelog && rm missing-changelog/CHANGELOG.md
cp -r valid-minimal missing-version && rm missing-version/VERSION
cd ~/prj_pri/paulsha-conventions
```

- [ ] **Step 3: 寫 R-01（README）的測試**

```python
# tests/test_rules.py
import pytest
from policy_check.config import load as load_config
from policy_check.rules.base import RuleContext, Status
from policy_check.rules import registry


def ctx_for(repo):
    conf = load_config(repo)
    return RuleContext(
        repo_root=repo,
        profile=conf["policy_profile"],
        policy_version=conf["policy_version"],
        config=conf,
    )


def run_rule(rule_id: str, ctx: RuleContext):
    rules = {r.rule_id: r for r in registry.load_all()}
    return rules[rule_id].check(ctx)


@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",   Status.PASS),
    ("missing-readme",  Status.FAIL),
])
def test_r01(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-01", ctx_for(repo))
    assert result.status == expected, result.message
```

- [ ] **Step 4: 跑測試確認 R-01 失敗（rule 尚未實作）**

```bash
pytest tests/test_rules.py::test_r01 -v
```

Expected: FAIL — KeyError 'R-01' because no rule registered.

- [ ] **Step 5: 實作 R-01**

```python
# policy_check/rules/r01_readme_exists.py
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


@register
class R01ReadmeExists:
    rule_id = "R-01"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        path = ctx.repo_root / "README.md"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "README.md not found at repo root")
        if path.stat().st_size < 100:
            return RuleResult(self.rule_id, Status.FAIL, f"README.md too short ({path.stat().st_size} bytes; need ≥100)")
        return RuleResult(self.rule_id, Status.PASS, "README.md present and non-empty")
```

- [ ] **Step 6: 跑 R-01 測試確認通過**

```bash
pytest tests/test_rules.py::test_r01 -v
```

Expected: 2 passed

- [ ] **Step 7: 實作並測試 R-03**

```python
# policy_check/rules/r03_changelog_exists.py
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


@register
class R03ChangelogExists:
    rule_id = "R-03"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        path = ctx.repo_root / "CHANGELOG.md"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "CHANGELOG.md not found at repo root")
        return RuleResult(self.rule_id, Status.PASS, "CHANGELOG.md present")
```

加測試：

```python
# 追加到 tests/test_rules.py
@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",     Status.PASS),
    ("missing-changelog", Status.FAIL),
])
def test_r03(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-03", ctx_for(repo))
    assert result.status == expected, result.message
```

Run: `pytest tests/test_rules.py::test_r03 -v` → 2 passed.

- [ ] **Step 8: 實作並測試 R-05**

```python
# policy_check/rules/r05_version_exists.py
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


@register
class R05VersionExists:
    rule_id = "R-05"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        path = ctx.repo_root / "VERSION"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "VERSION file not found at repo root")
        return RuleResult(self.rule_id, Status.PASS, "VERSION file present")
```

```python
# tests/test_rules.py 追加
@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",    Status.PASS),
    ("missing-version",  Status.FAIL),
])
def test_r05(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-05", ctx_for(repo))
    assert result.status == expected, result.message
```

Run: `pytest tests/test_rules.py::test_r05 -v` → 2 passed.

- [ ] **Step 9: Commit**

```bash
git add policy_check/rules/r01_readme_exists.py \
        policy_check/rules/r03_changelog_exists.py \
        policy_check/rules/r05_version_exists.py \
        tests/fixtures/valid-minimal tests/fixtures/missing-readme \
        tests/fixtures/missing-changelog tests/fixtures/missing-version \
        tests/test_rules.py
git commit -m "feat(rules): R-01/R-03/R-05 file existence checks + fixtures"
```

---

## Task 5: R-02 — README 必備段落

**Files:**
- Create: `policy_check/rules/r02_readme_sections.py`
- Create: `tests/fixtures/missing-readme-sections/`

- [ ] **Step 1: 建違規 fixture**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/missing-readme-sections
cat > tests/fixtures/missing-readme-sections/README.md <<'EOF'
# Sample repo with no required sections

This README is long enough to pass R-01 byte threshold but is missing
the required sections mandated by R-02.
EOF
```

- [ ] **Step 2: 寫測試**

```python
# tests/test_rules.py 追加
@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",             Status.PASS),
    ("missing-readme-sections",   Status.FAIL),
])
def test_r02(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-02", ctx_for(repo))
    assert result.status == expected, result.message
```

Run: `pytest tests/test_rules.py::test_r02 -v` → FAIL (R-02 not registered).

- [ ] **Step 3: 實作 R-02**

```python
# policy_check/rules/r02_readme_sections.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

REQUIRED_SECTIONS = ["Install", "Usage", "Version"]


@register
class R02ReadmeSections:
    rule_id = "R-02"
    exempt_label = "policy-exempt:readme-sections"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "exempt", exempt_label=self.exempt_label)
        path = ctx.repo_root / "README.md"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "README.md missing (see R-01)")
        text = path.read_text()
        headings = set(re.findall(r"^##\s+([^\n]+?)\s*$", text, flags=re.MULTILINE))
        missing = [s for s in REQUIRED_SECTIONS if s not in headings]
        if missing:
            return RuleResult(
                self.rule_id, Status.FAIL,
                f"README missing required sections: {missing}",
                detail=f"expected ## headings: {REQUIRED_SECTIONS}; found: {sorted(headings)}",
            )
        return RuleResult(self.rule_id, Status.PASS, f"README has all required sections: {REQUIRED_SECTIONS}")
```

Run: `pytest tests/test_rules.py::test_r02 -v` → 2 passed.

- [ ] **Step 4: Commit**

```bash
git add policy_check/rules/r02_readme_sections.py \
        tests/fixtures/missing-readme-sections tests/test_rules.py
git commit -m "feat(rules): R-02 README required sections check"
```

---

## Task 6: R-04 — CHANGELOG 格式

**Files:**
- Create: `policy_check/rules/r04_changelog_format.py`
- Create: `tests/fixtures/bad-changelog-format/`

- [ ] **Step 1: 建違規 fixture**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/bad-changelog-format
cat > tests/fixtures/bad-changelog-format/CHANGELOG.md <<'EOF'
# 這個 CHANGELOG 沒有 [Unreleased] section
Random text, no keep-a-changelog structure.
EOF
```

- [ ] **Step 2: 寫測試**

```python
@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",            Status.PASS),
    ("bad-changelog-format",     Status.FAIL),
])
def test_r04(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-04", ctx_for(repo))
    assert result.status == expected, result.message
```

Run → FAIL (R-04 not registered).

- [ ] **Step 3: 實作 R-04**

```python
# policy_check/rules/r04_changelog_format.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


@register
class R04ChangelogFormat:
    rule_id = "R-04"
    exempt_label = "policy-exempt:changelog-format"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "exempt", exempt_label=self.exempt_label)
        path = ctx.repo_root / "CHANGELOG.md"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "CHANGELOG.md missing (see R-03)")
        text = path.read_text()
        if not re.search(r"^#\s+Changelog", text, flags=re.MULTILINE):
            return RuleResult(self.rule_id, Status.FAIL, "CHANGELOG.md missing top-level `# Changelog` heading")
        if not re.search(r"^##\s+\[Unreleased\]", text, flags=re.MULTILINE):
            return RuleResult(self.rule_id, Status.FAIL, "CHANGELOG.md missing `## [Unreleased]` section")
        return RuleResult(self.rule_id, Status.PASS, "CHANGELOG has required Keep-a-Changelog structure")
```

Run: `pytest tests/test_rules.py::test_r04 -v` → 2 passed.

- [ ] **Step 4: Commit**

```bash
git add policy_check/rules/r04_changelog_format.py \
        tests/fixtures/bad-changelog-format tests/test_rules.py
git commit -m "feat(rules): R-04 CHANGELOG Keep-a-Changelog format check"
```

---

## Task 7: R-06/R-07 — VERSION 格式與 tag 一致

**Files:**
- Create: `policy_check/rules/r06_version_format.py`
- Create: `policy_check/rules/r07_version_tag_sync.py`
- Create: `tests/fixtures/bad-version-format/`
- Create: `tests/fixtures/version-tag-mismatch/`

- [ ] **Step 1: 建違規 fixtures**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/bad-version-format
echo "not-a-version" > tests/fixtures/bad-version-format/VERSION

cp -r tests/fixtures/valid-minimal tests/fixtures/version-tag-mismatch
echo "0.0.7" > tests/fixtures/version-tag-mismatch/VERSION
# tag 模擬在測試裡 inject（fixture 本身無 git repo），見 Step 2
```

- [ ] **Step 2: 寫測試**

```python
VERSION_RE = r"^\d+\.\d+\.\d+(-fix\.\d+)?$"

@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",         Status.PASS),
    ("bad-version-format",    Status.FAIL),
])
def test_r06(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-06", ctx_for(repo))
    assert result.status == expected, result.message


@pytest.mark.parametrize("fixture,latest_tag,labels,expected", [
    ("valid-minimal",          "v0.0.0",  [],                 Status.PASS),
    ("version-tag-mismatch",   "v0.0.3",  [],                 Status.FAIL),
    ("version-tag-mismatch",   "v0.0.3",  ["release:patch"],  Status.SKIP),
    ("valid-minimal",           None,     [],                 Status.PASS),  # 無 tag 視為 0.0.0 首發
])
def test_r07(fixture_repo, fixture, latest_tag, labels, expected):
    repo = fixture_repo(fixture)
    c = ctx_for(repo)
    c.latest_tag = latest_tag
    c.pr_labels = labels
    result = run_rule("R-07", c)
    assert result.status == expected, result.message
```

Run → FAIL。

- [ ] **Step 3: 實作 R-06**

```python
# policy_check/rules/r06_version_format.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-fix\.\d+)?$")


@register
class R06VersionFormat:
    rule_id = "R-06"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        path = ctx.repo_root / "VERSION"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "VERSION missing (see R-05)")
        content = path.read_text().strip()
        if not VERSION_RE.match(content):
            return RuleResult(
                self.rule_id, Status.FAIL,
                f"VERSION content does not match <MAJOR>.<MINOR>.<PATCH>[-fix.N]: {content!r}",
            )
        return RuleResult(self.rule_id, Status.PASS, f"VERSION format valid: {content}")
```

- [ ] **Step 4: 實作 R-07**

```python
# policy_check/rules/r07_version_tag_sync.py
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

RELEASE_LABELS = {"release:patch", "release:minor", "release:major"}


@register
class R07VersionTagSync:
    rule_id = "R-07"
    exempt_label = None   # 豁免藉由 release:* label，不是 policy-exempt

    def check(self, ctx: RuleContext) -> RuleResult:
        if any(l in RELEASE_LABELS for l in ctx.pr_labels):
            return RuleResult(self.rule_id, Status.SKIP, "release label present; VERSION may lead tag")
        path = ctx.repo_root / "VERSION"
        if not path.exists():
            return RuleResult(self.rule_id, Status.FAIL, "VERSION missing (see R-05)")
        version = path.read_text().strip()
        tag_norm = (ctx.latest_tag or "v0.0.0").lstrip("v").split("-fix.")[0]
        version_norm = version.split("-fix.")[0]
        if version_norm != tag_norm:
            return RuleResult(
                self.rule_id, Status.FAIL,
                f"VERSION {version} does not match latest tag {ctx.latest_tag}",
            )
        return RuleResult(self.rule_id, Status.PASS, f"VERSION {version} matches latest tag {ctx.latest_tag}")
```

Run: `pytest tests/test_rules.py::test_r06 tests/test_rules.py::test_r07 -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add policy_check/rules/r06_version_format.py \
        policy_check/rules/r07_version_tag_sync.py \
        tests/fixtures/bad-version-format tests/fixtures/version-tag-mismatch \
        tests/test_rules.py
git commit -m "feat(rules): R-06 VERSION format + R-07 version/tag sync"
```

---

## Task 8: R-08 — `.paul-project.yml` schema

**Files:**
- Create: `policy_check/rules/r08_paul_project_yml.py`
- Create: `tests/fixtures/missing-paul-project-yml/`
- Create: `tests/fixtures/incomplete-paul-project-yml/`

- [ ] **Step 1: 建違規 fixtures**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/missing-paul-project-yml
rm tests/fixtures/missing-paul-project-yml/.paul-project.yml

cp -r tests/fixtures/valid-minimal tests/fixtures/incomplete-paul-project-yml
cat > tests/fixtures/incomplete-paul-project-yml/.paul-project.yml <<EOF
policy_profile: flat
# 缺 policy_version
EOF
```

- [ ] **Step 2: 調整 `ctx_for` 以容忍 config 載入失敗**

```python
# tests/test_rules.py 頂端加 helper
from policy_check.config import ConfigError

def ctx_for(repo):
    try:
        conf = load_config(repo)
        return RuleContext(
            repo_root=repo,
            profile=conf["policy_profile"],
            policy_version=conf["policy_version"],
            config=conf,
        )
    except ConfigError:
        # R-08 自己會從磁碟再讀一次判定；其他 rule 不會被呼叫
        return RuleContext(repo_root=repo, profile="flat", policy_version="0.0.0")
```

- [ ] **Step 3: 寫測試**

```python
@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",                    Status.PASS),
    ("missing-paul-project-yml",         Status.FAIL),
    ("incomplete-paul-project-yml",      Status.FAIL),
])
def test_r08(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-08", ctx_for(repo))
    assert result.status == expected, result.message
```

- [ ] **Step 4: 實作 R-08**

```python
# policy_check/rules/r08_paul_project_yml.py
from policy_check.config import load as load_config, ConfigError
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


@register
class R08PaulProjectYml:
    rule_id = "R-08"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        try:
            load_config(ctx.repo_root)
        except ConfigError as e:
            return RuleResult(self.rule_id, Status.FAIL, str(e))
        return RuleResult(self.rule_id, Status.PASS, ".paul-project.yml valid")
```

Run: `pytest tests/test_rules.py::test_r08 -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add policy_check/rules/r08_paul_project_yml.py \
        tests/fixtures/missing-paul-project-yml \
        tests/fixtures/incomplete-paul-project-yml tests/test_rules.py
git commit -m "feat(rules): R-08 .paul-project.yml schema validation"
```

---

## Task 9: R-09 — Code 變動必有 CHANGELOG entry

**Files:**
- Create: `policy_check/rules/r09_code_changelog_sync.py`
- Create: `tests/fixtures/code-no-changelog/`
- Create: `tests/fixtures/code-changelog-synced/`

- [ ] **Step 1: 建違規 / 合規 fixtures**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/code-no-changelog
# CHANGELOG 的 [Unreleased] section 為空
cat > tests/fixtures/code-no-changelog/CHANGELOG.md <<'EOF'
# Changelog

## [Unreleased]

## [0.0.0] - 2026-04-22
EOF

cp -r tests/fixtures/valid-minimal tests/fixtures/code-changelog-synced
# 有 Unreleased entry
cat > tests/fixtures/code-changelog-synced/CHANGELOG.md <<'EOF'
# Changelog

## [Unreleased]

### Added
- new feature in code
EOF
```

- [ ] **Step 2: 寫測試**

```python
@pytest.mark.parametrize("fixture,changed_files,labels,expected", [
    # code 變動、CHANGELOG 有 entry → pass
    ("code-changelog-synced",   ["src/foo.py"], [],                Status.PASS),
    # code 變動、CHANGELOG 空 → fail
    ("code-no-changelog",       ["src/foo.py"], [],                Status.FAIL),
    # code 變動但有 skip-changelog → skip
    ("code-no-changelog",       ["src/foo.py"], ["skip-changelog"],Status.SKIP),
    # 只動 docs → pass
    ("code-no-changelog",       ["docs/x.md"],   [],               Status.PASS),
])
def test_r09(fixture_repo, fixture, changed_files, labels, expected):
    repo = fixture_repo(fixture)
    c = ctx_for(repo)
    c.changed_files = changed_files
    c.pr_labels = labels
    # config 需有 code_paths；valid-minimal profile=flat → 預設 ["**/*.py", ...]
    c.config = {**c.config, "code_paths": ["**/*.py", "**/*.sh", "scripts/**"]}
    result = run_rule("R-09", c)
    assert result.status == expected, result.message
```

- [ ] **Step 3: 實作 R-09**

```python
# policy_check/rules/r09_code_changelog_sync.py
import re
from fnmatch import fnmatch
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


def _unreleased_has_entry(changelog_text: str) -> bool:
    m = re.search(r"^##\s+\[Unreleased\](.*?)(?=^##\s+\[|\Z)", changelog_text,
                  flags=re.MULTILINE | re.DOTALL)
    if not m:
        return False
    body = m.group(1)
    # 至少一個非空 bullet / 非空 sub-section
    return bool(re.search(r"^\s*-\s+\S", body, flags=re.MULTILINE))


@register
class R09CodeChangelogSync:
    rule_id = "R-09"
    exempt_label = "skip-changelog"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "skip-changelog label present",
                              exempt_label=self.exempt_label)
        code_paths = ctx.config.get("code_paths", [])
        code_hit = any(
            any(fnmatch(f, pat) for pat in code_paths)
            for f in ctx.changed_files
        )
        if not code_hit:
            return RuleResult(self.rule_id, Status.PASS, "no code path files changed")
        changelog = ctx.repo_root / "CHANGELOG.md"
        if not changelog.exists():
            return RuleResult(self.rule_id, Status.FAIL, "code changed but CHANGELOG.md missing")
        if not _unreleased_has_entry(changelog.read_text()):
            return RuleResult(self.rule_id, Status.FAIL,
                              "code changed but [Unreleased] section has no entry")
        return RuleResult(self.rule_id, Status.PASS, "code change + Unreleased entry present")
```

Run: `pytest tests/test_rules.py::test_r09 -v` → 4 passed.

- [ ] **Step 4: Commit**

```bash
git add policy_check/rules/r09_code_changelog_sync.py \
        tests/fixtures/code-no-changelog tests/fixtures/code-changelog-synced \
        tests/test_rules.py
git commit -m "feat(rules): R-09 code change ↔ CHANGELOG sync"
```

---

## Task 10: R-10/R-11/R-12 — PR-property 規則

**Files:**
- Create: `policy_check/rules/r10_pr_title.py`
- Create: `policy_check/rules/r11_pr_body_checklist.py`
- Create: `policy_check/rules/r12_branch_source.py`

（此任務無 fixture 目錄；測試直接 mock PR 屬性）

- [ ] **Step 1: 寫測試**

```python
# tests/test_rules.py 追加

CC_TITLE_RE = r"^(feat|fix|docs|chore|refactor|test|style|perf|ci|build)(\([^)]+\))?: .+"

@pytest.mark.parametrize("title,labels,expected", [
    ("feat(core): add X",                         [],                           Status.PASS),
    ("feat: add Y",                               [],                           Status.PASS),
    ("bad title no prefix",                       [],                           Status.FAIL),
    ("bad title no prefix",                       ["policy-exempt:pr-title"],   Status.SKIP),
])
def test_r10(fixture_repo, title, labels, expected):
    repo = fixture_repo("valid-minimal")
    c = ctx_for(repo); c.pr_title = title; c.pr_labels = labels
    result = run_rule("R-10", c)
    assert result.status == expected, result.message


@pytest.mark.parametrize("body,labels,expected", [
    ("- [x] done\n- [x] done",                       [],        Status.PASS),
    ("- [x] one\n- [ ] another",                     [],        Status.FAIL),
    ("- [x] one\n- [ ] another",                     ["wip"],   Status.SKIP),
    ("no checkbox at all",                            [],        Status.PASS),  # 沒 checkbox 視為無需勾
])
def test_r11(fixture_repo, body, labels, expected):
    repo = fixture_repo("valid-minimal")
    c = ctx_for(repo); c.pr_body = body; c.pr_labels = labels
    result = run_rule("R-11", c)
    assert result.status == expected, result.message


@pytest.mark.parametrize("head,base,labels,expected", [
    ("feature/foo",                     "main",          [],                           Status.PASS),
    ("wt/foo/subtask",                  "feature/foo",   [],                           Status.PASS),
    ("random-branch",                   "main",          [],                           Status.FAIL),
    ("random-branch",                   "main",          ["policy-exempt:branch-name"],Status.SKIP),
    ("wt/foo/bar",                      "main",          [],                           Status.FAIL),
])
def test_r12(fixture_repo, head, base, labels, expected):
    repo = fixture_repo("valid-minimal")
    c = ctx_for(repo); c.pr_head_ref = head; c.pr_base_ref = base; c.pr_labels = labels
    result = run_rule("R-12", c)
    assert result.status == expected, result.message
```

- [ ] **Step 2: 實作 R-10**

```python
# policy_check/rules/r10_pr_title.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

CC_TITLE_RE = re.compile(r"^(feat|fix|docs|chore|refactor|test|style|perf|ci|build)(\([^)]+\))?: .+")


@register
class R10PrTitle:
    rule_id = "R-10"
    exempt_label = "policy-exempt:pr-title"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "exempt", exempt_label=self.exempt_label)
        if not ctx.pr_title:
            return RuleResult(self.rule_id, Status.PASS, "no PR title in context (non-PR run)")
        if not CC_TITLE_RE.match(ctx.pr_title):
            return RuleResult(self.rule_id, Status.FAIL,
                              f"PR title does not match conventional-commit: {ctx.pr_title!r}")
        return RuleResult(self.rule_id, Status.PASS, "PR title matches conventional-commit")
```

- [ ] **Step 3: 實作 R-11**

```python
# policy_check/rules/r11_pr_body_checklist.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


@register
class R11PrBodyChecklist:
    rule_id = "R-11"
    exempt_label = None  # wip label 走特別邏輯

    def check(self, ctx: RuleContext) -> RuleResult:
        if "wip" in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "wip label present", exempt_label="wip")
        if not ctx.pr_body:
            return RuleResult(self.rule_id, Status.PASS, "no PR body (non-PR run)")
        unchecked = re.findall(r"^\s*-\s+\[\s\]\s+.+$", ctx.pr_body, flags=re.MULTILINE)
        if unchecked:
            return RuleResult(self.rule_id, Status.FAIL,
                              f"PR body has {len(unchecked)} unchecked items",
                              detail="\n".join(unchecked))
        return RuleResult(self.rule_id, Status.PASS, "PR body has no unchecked items")
```

- [ ] **Step 4: 實作 R-12**

```python
# policy_check/rules/r12_branch_source.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

FEATURE_RE = re.compile(r"^feature/[a-z0-9][a-z0-9-]{0,59}$")
WT_RE      = re.compile(r"^wt/[a-z0-9][a-z0-9-]{0,59}/[a-z0-9][a-z0-9-]{0,59}$")


@register
class R12BranchSource:
    rule_id = "R-12"
    exempt_label = "policy-exempt:branch-name"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "exempt", exempt_label=self.exempt_label)
        head, base = ctx.pr_head_ref, ctx.pr_base_ref
        if not head or not base:
            return RuleResult(self.rule_id, Status.PASS, "no branch context (non-PR run)")
        if base == "main":
            ok = bool(FEATURE_RE.match(head))
            msg = f"target main requires feature/<slug>; got head={head!r}"
        elif base.startswith("feature/"):
            feat = base.split("/", 1)[1]
            ok = head.startswith(f"wt/{feat}/") and bool(WT_RE.match(head))
            msg = f"target {base!r} requires wt/{feat}/<subtask>; got head={head!r}"
        else:
            return RuleResult(self.rule_id, Status.FAIL, f"unexpected base branch {base!r}")
        return (RuleResult(self.rule_id, Status.PASS, f"branch source valid: {head} → {base}")
                if ok else RuleResult(self.rule_id, Status.FAIL, msg))
```

Run: `pytest tests/test_rules.py::test_r10 tests/test_rules.py::test_r11 tests/test_rules.py::test_r12 -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add policy_check/rules/r10_pr_title.py \
        policy_check/rules/r11_pr_body_checklist.py \
        policy_check/rules/r12_branch_source.py tests/test_rules.py
git commit -m "feat(rules): R-10/R-11/R-12 PR property checks"
```

---

## Task 11: R-13/R-14 — Agent convention files

**Files:**
- Create: `policy_check/rules/r13_agent_files_exist.py`
- Create: `policy_check/rules/r14_agent_files_version.py`
- Create: `tests/fixtures/missing-agent-files/`
- Create: `tests/fixtures/agent-version-mismatch/`

- [ ] **Step 1: 調整 valid-minimal 加 agent files**

```bash
cd tests/fixtures/valid-minimal
cat > CLAUDE.md <<'EOF'
<!-- managed-by: hamanpaul/paulsha-conventions@v1.0.0 -->
policy_version: 1.0.0
# Agent checklist stub
EOF
cp CLAUDE.md AGENTS.md
cp CLAUDE.md GEMINI.md
mkdir -p .github
cp CLAUDE.md .github/copilot-instructions.md
cd ~/prj_pri/paulsha-conventions
```

注意：此變動會連帶影響 Task 4-10 既有 fixture（它們都是 cp valid-minimal）。重新 regenerate：

```bash
# 刪除 Task 4-10 已建 fixtures 中有複製 valid-minimal 骨架的那幾個，改由此時點往後重生
for f in missing-readme missing-changelog missing-version missing-readme-sections \
         bad-changelog-format bad-version-format version-tag-mismatch \
         missing-paul-project-yml incomplete-paul-project-yml \
         code-no-changelog code-changelog-synced; do
  rm -rf tests/fixtures/$f
done
# 重跑 Task 4/5/6/7/8/9 的 fixture 建立步驟（只 fixture 部分，不重 commit）
```

> 註：此步驟是為了讓 valid-minimal 同時滿足 R-13。實務上本 step 應在 Task 4 之前先定好 valid-minimal 最終內容 — 若 executor 照順序跑，請改成在 Task 4 Step 1 就把 agent files 加入 valid-minimal，並跳過本 step 的刪檔重生。

- [ ] **Step 2: 建 R-13/R-14 違規 fixtures**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/missing-agent-files
rm tests/fixtures/missing-agent-files/CLAUDE.md

cp -r tests/fixtures/valid-minimal tests/fixtures/agent-version-mismatch
sed -i 's/policy_version: 1.0.0/policy_version: 0.9.0/' \
    tests/fixtures/agent-version-mismatch/CLAUDE.md
```

- [ ] **Step 3: 寫測試**

```python
AGENT_FILES = ["CLAUDE.md", "AGENTS.md", "GEMINI.md", ".github/copilot-instructions.md"]

@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",         Status.PASS),
    ("missing-agent-files",   Status.FAIL),
])
def test_r13(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-13", ctx_for(repo))
    assert result.status == expected, result.message


@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",             Status.PASS),
    ("agent-version-mismatch",    Status.FAIL),
])
def test_r14(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-14", ctx_for(repo))
    assert result.status == expected, result.message
```

- [ ] **Step 4: 實作 R-13**

```python
# policy_check/rules/r13_agent_files_exist.py
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

AGENT_FILES = ["CLAUDE.md", "AGENTS.md", "GEMINI.md", ".github/copilot-instructions.md"]


@register
class R13AgentFilesExist:
    rule_id = "R-13"
    exempt_label = "policy-exempt:agent-files"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "exempt", exempt_label=self.exempt_label)
        missing = [f for f in AGENT_FILES if not (ctx.repo_root / f).exists()]
        if missing:
            return RuleResult(self.rule_id, Status.FAIL, f"missing agent convention files: {missing}")
        return RuleResult(self.rule_id, Status.PASS, "all agent convention files present")
```

- [ ] **Step 5: 實作 R-14**

```python
# policy_check/rules/r14_agent_files_version.py
import re
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register
from policy_check.rules.r13_agent_files_exist import AGENT_FILES

VER_RE = re.compile(r"policy_version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:-fix\.\d+)?)")


@register
class R14AgentFilesVersion:
    rule_id = "R-14"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        declared = ctx.policy_version
        mismatches = []
        for fname in AGENT_FILES:
            p = ctx.repo_root / fname
            if not p.exists():
                continue  # R-13 會擋
            m = VER_RE.search(p.read_text())
            if not m:
                mismatches.append(f"{fname}: policy_version not declared")
            elif m.group(1) != declared:
                mismatches.append(f"{fname}: policy_version {m.group(1)} != declared {declared}")
        if mismatches:
            return RuleResult(self.rule_id, Status.FAIL, "agent file version drift",
                              detail="\n".join(mismatches))
        return RuleResult(self.rule_id, Status.PASS, f"agent files aligned to policy_version {declared}")
```

Run: `pytest tests/test_rules.py::test_r13 tests/test_rules.py::test_r14 -v` → all pass.

- [ ] **Step 6: Commit**

```bash
git add policy_check/rules/r13_agent_files_exist.py \
        policy_check/rules/r14_agent_files_version.py \
        tests/fixtures/missing-agent-files tests/fixtures/agent-version-mismatch \
        tests/fixtures/valid-minimal tests/test_rules.py
git commit -m "feat(rules): R-13/R-14 agent convention file existence + version alignment"
```

---

## Task 12: R-15 — Workflow `uses:` tag/SHA pinning

**Files:**
- Create: `policy_check/rules/r15_workflow_pinning.py`
- Create: `tests/fixtures/branch-ref-workflow/`
- Create: `tests/fixtures/valid-minimal/.github/workflows/policy-check.yml`（補進 valid-minimal）

- [ ] **Step 1: 補 valid-minimal 的 workflow**

```bash
mkdir -p tests/fixtures/valid-minimal/.github/workflows
cat > tests/fixtures/valid-minimal/.github/workflows/policy-check.yml <<'EOF'
name: policy-check
on: [pull_request]
jobs:
  check:
    uses: hamanpaul/paulsha-conventions/.github/workflows/reusable-policy-check.yml@v1
    with:
      policy_profile: flat
      policy_version: 1.0.0
EOF
```

- [ ] **Step 2: 建違規 fixture**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/branch-ref-workflow
sed -i 's/@v1$/@main/' tests/fixtures/branch-ref-workflow/.github/workflows/policy-check.yml
```

- [ ] **Step 3: 寫測試**

```python
@pytest.mark.parametrize("fixture,expected", [
    ("valid-minimal",          Status.PASS),
    ("branch-ref-workflow",    Status.FAIL),
])
def test_r15(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-15", ctx_for(repo))
    assert result.status == expected, result.message
```

- [ ] **Step 4: 實作 R-15**

```python
# policy_check/rules/r15_workflow_pinning.py
import re
from pathlib import Path
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register

USES_RE = re.compile(r"uses:\s*([^\s#]+)@([^\s#]+)")
BANNED_REFS = {"main", "master", "develop", "trunk"}
TAG_RE = re.compile(r"^v?\d+(\.\d+){0,2}(-[\w.-]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _classify(ref: str) -> str:
    if SHA_RE.match(ref):
        return "sha"
    if TAG_RE.match(ref):
        return "tag"
    if ref in BANNED_REFS:
        return "branch"
    # 模糊情境：保守視為 branch
    return "branch"


@register
class R15WorkflowPinning:
    rule_id = "R-15"
    exempt_label = None

    def check(self, ctx: RuleContext) -> RuleResult:
        wf_dir = ctx.repo_root / ".github/workflows"
        if not wf_dir.exists():
            return RuleResult(self.rule_id, Status.PASS, "no workflows")
        offenders = []
        for yml in wf_dir.glob("*.yml"):
            for line_no, line in enumerate(yml.read_text().splitlines(), 1):
                m = USES_RE.search(line)
                if not m:
                    continue
                repo_ref, ref = m.group(1), m.group(2)
                if repo_ref.startswith("./"):
                    continue  # 本 repo 的 composite action
                if _classify(ref) == "branch":
                    offenders.append(f"{yml.name}:{line_no} uses {repo_ref}@{ref} (branch ref not allowed)")
        if offenders:
            return RuleResult(self.rule_id, Status.FAIL, "workflow uses branch ref",
                              detail="\n".join(offenders))
        return RuleResult(self.rule_id, Status.PASS, "all workflow uses tag or SHA")
```

Run: `pytest tests/test_rules.py::test_r15 -v` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add policy_check/rules/r15_workflow_pinning.py \
        tests/fixtures/valid-minimal/.github \
        tests/fixtures/branch-ref-workflow tests/test_rules.py
git commit -m "feat(rules): R-15 workflow uses tag/SHA pinning"
```

---

## Task 13: R-16 — CLI help 同步

**Files:**
- Create: `policy_check/rules/r16_cli_help_sync.py`
- Create: `tests/fixtures/cli-empty/`
- Create: `tests/fixtures/cli-help-synced/`
- Create: `tests/fixtures/cli-help-mismatch/`
- Create: `tests/fixtures/cli-help-missing-marker/`
- Create: `tests/test_cli_help.py`

- [ ] **Step 1: 建 cli-empty fixture**

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/cli-empty
# .paul-project.yml 不含 cli: ← valid-minimal 本來就沒有 cli，符合要求
```

- [ ] **Step 2: 建 cli-help-synced fixture**

用一個可控的 echo-based「假 CLI」以避免測試時裝外部包：

```bash
cp -r tests/fixtures/valid-minimal tests/fixtures/cli-help-synced

# 寫入 .paul-project.yml 帶 cli 宣告
cat > tests/fixtures/cli-help-synced/.paul-project.yml <<'EOF'
policy_profile: flat
policy_version: 1.0.0
cli:
  - command: "echo"
    help_args: ["--help-demo"]
    reflected_in: "README.md"
    marker: "demo"
EOF

# echo --help-demo 會回 "--help-demo\n"（BSD/GNU echo 行為一致）
# 在 README 的 Usage 塞進一模一樣的 marker 區塊
cat > tests/fixtures/cli-help-synced/README.md <<'EOF'
# Sample
Placeholder over 100 bytes to satisfy R-01 size floor of the readme file content.

## Install
x

## Usage

<!-- BEGIN: cli-help marker="demo" -->
--help-demo
<!-- END: cli-help marker="demo" -->

## Version
0.0.0
EOF
```

- [ ] **Step 3: 建 mismatch / missing-marker fixtures**

```bash
cp -r tests/fixtures/cli-help-synced tests/fixtures/cli-help-mismatch
# 把 marker 內容改成不相符的
sed -i 's|--help-demo|WRONG OUTPUT|' tests/fixtures/cli-help-mismatch/README.md

cp -r tests/fixtures/cli-help-synced tests/fixtures/cli-help-missing-marker
# 刪掉 END marker
sed -i '/END: cli-help/d' tests/fixtures/cli-help-missing-marker/README.md
```

- [ ] **Step 4: 寫測試**

```python
# tests/test_cli_help.py
import pytest
from tests.test_rules import run_rule, ctx_for
from policy_check.rules.base import Status


@pytest.mark.parametrize("fixture,expected", [
    ("cli-empty",                Status.PASS),
    ("cli-help-synced",          Status.PASS),
    ("cli-help-mismatch",        Status.FAIL),
    ("cli-help-missing-marker",  Status.FAIL),
])
def test_r16(fixture_repo, fixture, expected):
    repo = fixture_repo(fixture)
    result = run_rule("R-16", ctx_for(repo))
    assert result.status == expected, result.message


def test_r16_exempt_label(fixture_repo):
    repo = fixture_repo("cli-help-mismatch")
    c = ctx_for(repo); c.pr_labels = ["policy-exempt:cli-help"]
    result = run_rule("R-16", c)
    assert result.status == Status.SKIP
```

- [ ] **Step 5: 實作 R-16**

```python
# policy_check/rules/r16_cli_help_sync.py
import os
import re
import subprocess
from pathlib import Path
from policy_check.rules.base import Rule, RuleContext, RuleResult, Status
from policy_check.rules.registry import register


def _extract_marker(text: str, marker: str) -> tuple[bool, str]:
    begin = re.search(rf"<!--\s*BEGIN:\s*cli-help\s+marker=\"{re.escape(marker)}\"\s*-->", text)
    end   = re.search(rf"<!--\s*END:\s*cli-help\s+marker=\"{re.escape(marker)}\"\s*-->", text)
    if not begin or not end or end.start() < begin.end():
        return False, ""
    return True, text[begin.end():end.start()]


def _normalize(s: str) -> str:
    return s.strip()


@register
class R16CliHelpSync:
    rule_id = "R-16"
    exempt_label = "policy-exempt:cli-help"

    def check(self, ctx: RuleContext) -> RuleResult:
        if self.exempt_label in ctx.pr_labels:
            return RuleResult(self.rule_id, Status.SKIP, "exempt", exempt_label=self.exempt_label)
        entries = ctx.config.get("cli") or []
        if not entries:
            return RuleResult(self.rule_id, Status.PASS, "no CLI declared")
        env = {**os.environ, "LC_ALL": "C"}
        fails = []
        for e in entries:
            install = e.get("install_cmd")
            if install:
                r = subprocess.run(install, shell=True, cwd=ctx.repo_root, env=env, capture_output=True)
                if r.returncode != 0:
                    fails.append(f"install_cmd failed: {install}\n{r.stderr.decode('utf-8', 'replace')}")
                    continue
            exit_ok = e.get("exit_ok", [0])
            cmd = [e["command"]] + list(e.get("help_args", ["--help"]))
            r = subprocess.run(cmd, cwd=ctx.repo_root, env=env, capture_output=True, shell=False)
            if r.returncode not in exit_ok:
                fails.append(f"{e['command']} exit={r.returncode} not in {exit_ok}")
                continue
            actual = _normalize((r.stdout + r.stderr).decode("utf-8", "replace"))
            target = ctx.repo_root / e["reflected_in"]
            if not target.exists():
                fails.append(f"reflected_in not found: {e['reflected_in']}")
                continue
            ok, block = _extract_marker(target.read_text(), e["marker"])
            if not ok:
                fails.append(f"marker missing/invalid: marker={e['marker']!r} in {e['reflected_in']}")
                continue
            if _normalize(block) != actual:
                fails.append(f"diff for marker={e['marker']!r}:\n--- doc\n{block.strip()}\n+++ actual\n{actual}")
        if fails:
            return RuleResult(self.rule_id, Status.FAIL, "CLI help out of sync", detail="\n\n".join(fails))
        return RuleResult(self.rule_id, Status.PASS, f"{len(entries)} CLI entries in sync")
```

Run: `pytest tests/test_cli_help.py -v` → all pass.

- [ ] **Step 6: Commit**

```bash
git add policy_check/rules/r16_cli_help_sync.py \
        tests/fixtures/cli-empty tests/fixtures/cli-help-synced \
        tests/fixtures/cli-help-mismatch tests/fixtures/cli-help-missing-marker \
        tests/test_cli_help.py
git commit -m "feat(rules): R-16 CLI help sync with docs marker"
```

---

## Task 14: Composite action + reusable workflow YAML

**Files:**
- Create: `.github/actions/policy-check/action.yml`
- Create: `.github/actions/policy-check/run.sh`
- Create: `.github/workflows/reusable-policy-check.yml`
- Create: `.github/workflows/policy-check.yml`（dog-food caller）
- Create: `.github/workflows/self-test.yml`

- [ ] **Step 1: 寫 composite action**

```yaml
# .github/actions/policy-check/action.yml
name: policy-check
description: Run paulsha-conventions policy checks
inputs:
  profile:
    required: true
  version:
    required: true
runs:
  using: composite
  steps:
    - shell: bash
      run: ${{ github.action_path }}/run.sh "${{ inputs.profile }}" "${{ inputs.version }}"
```

```bash
# .github/actions/policy-check/run.sh
#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:?profile required}"
VERSION="${2:?version required}"

python3 -m pip install --quiet "policy-check @ git+https://github.com/hamanpaul/paulsha-conventions@v1"
python3 -m policy_check --repo "$GITHUB_WORKSPACE"
```

```bash
chmod +x .github/actions/policy-check/run.sh
```

- [ ] **Step 2: 寫 reusable workflow**

```yaml
# .github/workflows/reusable-policy-check.yml
name: policy-check (reusable)
on:
  workflow_call:
    inputs:
      policy_profile:
        type: string
        required: true
      policy_version:
        type: string
        required: true

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: ./.github/actions/policy-check
        with:
          profile: ${{ inputs.policy_profile }}
          version: ${{ inputs.policy_version }}
```

- [ ] **Step 3: 寫 dog-food caller**

```yaml
# .github/workflows/policy-check.yml
name: policy-check
on: [pull_request]
jobs:
  check:
    uses: ./.github/workflows/reusable-policy-check.yml
    with:
      policy_profile: flat
      policy_version: 1.0.0
```

- [ ] **Step 4: 寫 self-test workflow**

```yaml
# .github/workflows/self-test.yml
name: self-test
on: [push, pull_request]
jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[test]"
      - run: pytest -v
```

- [ ] **Step 5: 本地模擬 composite action（不透過 GitHub）**

```bash
# 測 composite action 的 run.sh 能呼叫 python 模組（不做 pip install，因為本地 -e 已裝）
python3 -m policy_check --repo tests/fixtures/valid-minimal
```

Expected: `pass: N / fail: 0 / skip: M`（N+M 應等於 15，R-16 對 valid-minimal 應 pass 因為無 cli）

- [ ] **Step 6: Commit**

```bash
git add .github/actions/policy-check .github/workflows
git commit -m "feat(ci): add composite action + reusable workflow + self-test"
```

---

## Task 15: Helper scripts

**Files:**
- Create: `scripts/update-cli-help.sh`
- Create: `scripts/apply-branch-protection.sh`
- Create: `scripts/worktree-cleanup.sh`

- [ ] **Step 1: 寫 update-cli-help.sh**

```bash
#!/usr/bin/env bash
# scripts/update-cli-help.sh
# 讀 .paul-project.yml.cli，實跑每個 command 更新對應 marker 區塊
set -euo pipefail
export LC_ALL=C

REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

python3 - <<'PY'
import os, subprocess, re, yaml, sys
from pathlib import Path

conf = yaml.safe_load(Path(".paul-project.yml").read_text())
entries = conf.get("cli") or []
if not entries:
    print("no cli entries; nothing to do")
    sys.exit(0)

for e in entries:
    if e.get("install_cmd"):
        subprocess.check_call(e["install_cmd"], shell=True)
    cmd = [e["command"]] + list(e.get("help_args", ["--help"]))
    out = subprocess.run(cmd, capture_output=True, text=True)
    actual = (out.stdout + out.stderr).strip()
    target = Path(e["reflected_in"])
    text = target.read_text()
    marker = re.escape(e["marker"])
    pattern = re.compile(
        rf"(<!--\s*BEGIN:\s*cli-help\s+marker=\"{marker}\"\s*-->)(.*?)(<!--\s*END:\s*cli-help\s+marker=\"{marker}\"\s*-->)",
        flags=re.DOTALL,
    )
    if not pattern.search(text):
        print(f"WARN: marker {e['marker']!r} not found in {e['reflected_in']}; skipping")
        continue
    new = pattern.sub(rf"\1\n{actual}\n\3", text)
    target.write_text(new)
    print(f"updated {e['reflected_in']} marker={e['marker']}")
PY
```

```bash
chmod +x scripts/update-cli-help.sh
```

- [ ] **Step 2: 寫 apply-branch-protection.sh**

```bash
#!/usr/bin/env bash
# scripts/apply-branch-protection.sh
# 套用 spec §3.4 的 branch protection 到當前 repo 的 main
set -euo pipefail

REPO="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
echo "Applying branch protection to ${REPO}:main ..."

gh api -X PUT "repos/${REPO}/branches/main/protection" \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks[strict]=true \
  -f required_status_checks[contexts][]="policy-check" \
  -F enforce_admins=false \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -F required_conversation_resolution=true \
  -F allow_force_pushes=false \
  -F allow_deletions=false \
  -F required_linear_history=false \
  > /dev/null

echo "Done."
```

```bash
chmod +x scripts/apply-branch-protection.sh
```

- [ ] **Step 3: 寫 worktree-cleanup.sh**

```bash
#!/usr/bin/env bash
# scripts/worktree-cleanup.sh
# 列出已合併回 base 的 wt/* 分支與對應 worktree；--apply 實際刪除
set -euo pipefail

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

git fetch --prune --quiet origin || true
MAIN_SHA=$(git rev-parse origin/main)

git worktree list --porcelain | awk '/^worktree/{wt=$2} /^branch/{print wt" "$2}' | \
while read -r wt branch; do
  [[ "$branch" == refs/heads/wt/* ]] || continue
  # 判斷 branch 是否已 merge 到 origin/main
  if git merge-base --is-ancestor "$branch" "$MAIN_SHA" 2>/dev/null; then
    if [[ $APPLY -eq 1 ]]; then
      echo "Removing worktree $wt (branch $branch)"
      git worktree remove --force "$wt"
      git branch -D "${branch#refs/heads/}"
    else
      echo "[dry] would remove $wt ($branch)"
    fi
  fi
done

echo "Done. Run with --apply to execute."
```

```bash
chmod +x scripts/worktree-cleanup.sh
```

- [ ] **Step 4: Commit**

```bash
git add scripts/
git commit -m "feat(scripts): update-cli-help / apply-branch-protection / worktree-cleanup"
```

---

## Task 16: Self dog-food — 讓 conventions 通過自己的 policy

**Files:**
- Modify: `~/prj_pri/paulsha-conventions/README.md`
- Modify: `~/prj_pri/paulsha-conventions/CHANGELOG.md`
- Modify: `~/prj_pri/paulsha-conventions/.paul-project.yml`
- Create: `~/prj_pri/paulsha-conventions/CLAUDE.md` / `AGENTS.md` / `GEMINI.md`
- Create: `~/prj_pri/paulsha-conventions/.github/copilot-instructions.md`

- [ ] **Step 1: 建 .paul-project.yml（自我宣告）**

```yaml
# ~/prj_pri/paulsha-conventions/.paul-project.yml
policy_profile: flat
policy_version: 1.0.0
code_paths:
  - "policy_check/**/*.py"
  - "scripts/**"
# 未來可宣告 cli: 以 dog-food R-16；初版先留空
```

- [ ] **Step 2: 寫 README（含必備段落）**

```markdown
# paulsha-conventions

Cross-repo policy for all `hamanpaul/*` GitHub repositories.
Defines version scheme, branch/PR rules, docs-sync checks, and the
`policy-check` reusable GitHub Action.

## Install

For downstream repos, add this caller workflow:

```yaml
# .github/workflows/policy-check.yml
on: [pull_request]
jobs:
  policy:
    uses: hamanpaul/paulsha-conventions/.github/workflows/reusable-policy-check.yml@v1
    with:
      policy_profile: flat           # or stage-driven
      policy_version: 1.0.0
```

## Usage

See `docs/` for the full policy text. Key concepts:

- `.paul-project.yml` at repo root declares profile + policy version
- Rules R-01 through R-16 (see spec) are enforced by the reusable workflow
- Breaking changes to policy bump MAJOR; downstream pins via `@v1`

## Version

Current: 1.0.0 (see `VERSION` file and `CHANGELOG.md`).
```

- [ ] **Step 3: 寫 CHANGELOG（Unreleased + v1.0.0 預備 entry）**

```markdown
# Changelog

All notable changes to this project will be documented in this file.
The format is based on Keep a Changelog, and this project adheres to
the `hamanpaul` project policy 1.0.0 (itself).

## [Unreleased]

## [1.0.0] - 2026-04-22

### Added
- Policy-check engine: 16 rules (R-01 through R-16)
- Composite action + reusable workflow
- Helper scripts: update-cli-help, apply-branch-protection, worktree-cleanup
- Self-test harness with fixture-based rule tests

[Unreleased]: https://github.com/hamanpaul/paulsha-conventions/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/hamanpaul/paulsha-conventions/releases/tag/v1.0.0
```

- [ ] **Step 4: 建 agent convention files**

```bash
cd ~/prj_pri/paulsha-conventions
cat > CLAUDE.md <<'EOF'
<!-- managed-by: hamanpaul/paulsha-conventions@v1.0.0 -->
<!-- 若修改此檔，同步更新 CLAUDE.md / AGENTS.md / GEMINI.md / .github/copilot-instructions.md 四份 -->

# Agent Policy Checklist

本 repo 受 hamanpaul project policy v1.0.0 管轄。
policy_profile: flat
policy_version: 1.0.0

## 動工前
- [ ] 分支不是 main（開 `feature/<slug>` 或 `wt/<feature>/<subtask>`）

## 改 code 時
- [ ] `CHANGELOG.md [Unreleased]` 同步更新（或標 `skip-changelog`）

## 完成前
- [ ] 測試全綠：`pytest -v`
- [ ] `python -m policy_check --repo .` 無 fail
- [ ] PR body checklist 全勾
EOF

cp CLAUDE.md AGENTS.md
cp CLAUDE.md GEMINI.md
mkdir -p .github
cp CLAUDE.md .github/copilot-instructions.md
```

- [ ] **Step 5: 更新 VERSION（對齊 CHANGELOG）**

```bash
echo "1.0.0" > VERSION
```

- [ ] **Step 6: 本地跑 policy-check（dog-food）**

```bash
cd ~/prj_pri/paulsha-conventions
python3 -m policy_check --repo .
```

Expected: 所有 rule pass 或 skip；exit code 0。
- R-07 因無 tag，邏輯「視 0.0.0 為隱式 tag」但 VERSION=1.0.0 會 mismatch → 需手動建 tag 或接受 fail。解法：

```bash
git add .
git commit -m "docs: self dog-food (README, CHANGELOG, agent files, VERSION)"
git tag -a v1.0.0 -m "v1.0.0"
python3 -m policy_check --repo .
```

現在 R-07 應 pass。

- [ ] **Step 7: 跑完整 pytest 確認沒 regression**

```bash
pytest -v
```

Expected: all pass（含 Task 4-13 的所有 parametrized cases）。

- [ ] **Step 8: 更新 CHANGELOG Unreleased 提到本次 dog-food commit（如有新增）**

（若 Step 6 commit 後再無後續 code 變動，Unreleased 可保持空；R-09 在本地跑時無 PR context，不會判 fail。）

- [ ] **Step 9: Final commit**

```bash
git add .
git commit -m "chore: conventions self dog-food pass (policy 1.0.0)" || true
```

---

## Self-Review（plan 完成後 executor 不需做，寫 plan 時已執行）

本節記錄 plan 撰寫時的自審結果。

### 1. Spec 涵蓋度
- spec §1（3-repo 架構）→ 本 plan 只涵蓋 conventions；template + .github 留 Plan 2 ✓
- spec §2（版號 / CHANGELOG / release trigger）→ R-04/R-06/R-07 + CHANGELOG 結構在 Task 6/7/16 ✓；release workflow 實作留 Plan 2
- spec §3（branch/PR/worktree）→ R-10/R-11/R-12 Task 10 ✓；branch protection script Task 15 ✓
- spec §4.2（R-01 ~ R-16）→ Task 4-13 全數覆蓋 ✓
- spec §4.3（Agent checklist 4 份）→ Task 11 fixture + Task 16 self dog-food ✓
- spec §4.6（R-16 CLI help）→ Task 13 ✓
- spec §5.1（template 內容）→ 留 Plan 2
- spec §5.2（建立新 repo 動作）→ 留 Plan 2
- spec §5.3（paulshaclaw migration）→ 屬 spec-2
- spec §5.4（meta-testing）→ 各 Task 的 fixture 直接實現 ✓；self-test workflow Task 14 ✓
- spec §5.5（tag/SHA pinning）→ R-15 Task 12 ✓
- spec §5.6（policy 演進）→ 非 code；policy 文本放 README/docs，本 plan 不細化
- spec §5.7（memory entry）→ 留 Plan 2（需要 conventions repo URL 穩定後再寫）
- spec §6（Acceptance）→ 第 2 條（conventions self dog-food）Task 16 ✓；第 3/4/5/6/7 留 Plan 2

### 2. Placeholder scan
- 無 TBD/TODO/later
- 所有 code block 為完整可執行
- 所有 regex 已提供

### 3. Type 一致
- `RuleContext` 欄位在 Task 2 定義，Task 3-13 使用一致
- `RuleResult(rule_id, status, message, detail, exempt_label)` 5 欄位全程一致
- `Rule` protocol 的 `rule_id` 為字串、`check()` 回 `RuleResult` — 一致

### 4. 風險與注意
- Task 11 Step 1 的「改 valid-minimal 會影響先前 fixtures」是流水線跑 plan 時的頭痛點 — 已在步驟註記建議 executor 把 valid-minimal 最終內容提早（Task 4 Step 1）建好，就不必重生。
- R-15 `_classify` 模糊情境保守判 branch — 若下游遇到非常規 ref（例 `releases/v1`）會被誤擋；policy v1 先嚴，未來用 allowlist 機制處理。
- R-16 本地測試使用 `echo --help-demo` 作為假 CLI，避免依賴外部包；真正的下游使用時由 `install_cmd` 負責裝對應專案。

---

## 下一步：Plan 2（待本 plan 落地後）

Plan 2 將涵蓋：
- `hamanpaul/.github` repo（community health files）
- `hamanpaul/paul-project-template` repo 建立與內容
- 三個 repo 推上 GitHub、建立 `v1`、`v1.0.0` tag
- Memory entry 寫入
- spec §6 acceptance 第 3-7 條的驗證

---

**Plan 完成並存於** `docs/superpowers/plans/2026-04-22-paulsha-conventions.md`。

### 兩種執行選項

1. **Subagent-Driven（推薦）** — 為每個 Task 派獨立 subagent，task 之間 review，快速迭代
2. **Inline Execution** — 在本 session 以 `executing-plans` 批次執行，含檢查點

哪一種？
