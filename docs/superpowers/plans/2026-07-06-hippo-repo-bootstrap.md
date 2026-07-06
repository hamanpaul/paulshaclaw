# paulsha-hippo Repo Bootstrap 實作計劃（#125 Phase 1 先行段）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `hamanpaul/paulsha-hippo` repo 骨架（template + conventions 1.0.12 + CLI stub + lib 隔離護欄 + deident gate + README 草稿），不搬任何 memory 程式碼。

**Architecture:** 依 `docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md`。本計劃只涵蓋 openspec change `memory-extraction-hippo` tasks.md 的 §1（先行，不必等閘）；§3 hippo 遷入與 §4 主 repo 遷移受站穩閘約束，閘清後各出獨立計劃。

**Tech Stack:** Python 3.10+（CI 3.12）、pytest、gh CLI、paulsha-conventions 1.0.12（reusable workflow）、GitHub rulesets。

## Global Constraints

- 新 repo 首發為 **private**；轉 public 前必過 deident sanitize（#201 / R-21）。
- conventions 引擎 pin：`58290153a400926851afa0f1794236e7669847c6`（v1.0.12，與主 repo `policy-check.yml` 相同）。
- agent 檔採 **symlink 模式**（R-14）：AGENTS.md／GEMINI.md／.github/copilot-instructions.md → CLAUDE.md。
- 所有文件 zh-tw；commit 訊息 conventional（zh-tw 主題）。
- `paulsha_hippo/lib/` 禁止 import `paulsha_hippo.lib.*` 以外的 `paulsha_hippo.*`（spec §3.2）。
- 分支 slug 不得含小數點。
- repo 工作目錄：`~/prj_pri/paulsha-hippo`。

---

### Task 1: 建立 repo、驗 symlink、上 tag 保護

**Files:**
- Create: GitHub repo `hamanpaul/paulsha-hippo`（from template）
- Create: local clone `~/prj_pri/paulsha-hippo`

**Interfaces:**
- Consumes: `hamanpaul/new-project-template`（含 `.paul-project.yml`、`policy-check.yml`、`tests.yml`、agent 檔、`VERSION=0.0.0`）
- Produces: 可 push 的 clone + `feature/bootstrap` 分支（後續 Task 全部在此分支上）

- [ ] **Step 1: 從 template 建 private repo**

```bash
gh repo create hamanpaul/paulsha-hippo \
  --template hamanpaul/new-project-template \
  --private \
  --description "跨 LLM vendor 的經驗筆記基座：session 蒸餾、dream 整理、wakeup 回灌"
```

Expected: 輸出 `https://github.com/hamanpaul/paulsha-hippo`

- [ ] **Step 2: clone 並驗證 agent 檔 symlink 未被 template 產生器破壞**

```bash
git clone git@github.com:hamanpaul/paulsha-hippo.git ~/prj_pri/paulsha-hippo
cd ~/prj_pri/paulsha-hippo
ls -la AGENTS.md GEMINI.md .github/copilot-instructions.md
```

Expected: 三者皆為 `-> CLAUDE.md`（copilot 為 `-> ../CLAUDE.md`）的 symlink。
若為一般檔案（template 產生器展開了 symlink），修復：

```bash
rm AGENTS.md GEMINI.md .github/copilot-instructions.md
ln -s CLAUDE.md AGENTS.md && ln -s CLAUDE.md GEMINI.md && ln -s ../CLAUDE.md .github/copilot-instructions.md
```

- [ ] **Step 3: 上 version tag 保護 ruleset（spec §2：protected tags）**

```bash
gh api repos/hamanpaul/paulsha-hippo/rulesets --method POST --input - <<'EOF'
{"name":"protect-version-tags","target":"tag","enforcement":"active",
 "conditions":{"ref_name":{"include":["refs/tags/v*"],"exclude":[]}},
 "rules":[{"type":"deletion"},{"type":"update"}]}
EOF
```

Expected: 回傳 JSON 含 `"id"` 與 `"enforcement": "active"`

- [ ] **Step 4: 開工作分支**

```bash
cd ~/prj_pri/paulsha-hippo && git checkout -b feature/bootstrap
```

Expected: `Switched to a new branch 'feature/bootstrap'`

---

### Task 2: conventions 引擎升 1.0.12 並本機實跑零 fail

**Files:**
- Modify: `~/prj_pri/paulsha-hippo/.paul-project.yml`
- Modify: `~/prj_pri/paulsha-hippo/.github/workflows/policy-check.yml`
- Modify: `~/prj_pri/paulsha-hippo/CHANGELOG.md`

**Interfaces:**
- Consumes: template 出廠檔（pin v1.0.7 `e24fbd679d35d04a79ea21aff7733fadebd5e77e`）
- Produces: `policy_version: 1.0.12` 全 repo 一致（R-20 由 CI 驗）

- [ ] **Step 1: 改 `.paul-project.yml`**

整檔改為：

```yaml
policy_profile: flat
policy_version: 1.0.12
code_paths:
  - ".paul-project.yml"
  - "VERSION"
  - "pyproject.toml"
  - "paulsha_hippo/**"
  - "scripts/**"
  - "tests/**"
  - "**/*.md"
  - "**/*.yml"
  - "**/*.yaml"
  - ".github/**"
agent_files:
  mode: symlink
conventions_engine:
  repo: hamanpaul/paulsha-conventions
```

- [ ] **Step 2: 改 `policy-check.yml` 的 pin 與版本（三處一致）**

```yaml
name: Policy Check

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  policy:
    uses: hamanpaul/paulsha-conventions/.github/workflows/reusable-policy-check.yml@58290153a400926851afa0f1794236e7669847c6  # v1.0.12
    with:
      policy_profile: flat
      policy_version: "1.0.12"
      policy_engine_ref: 58290153a400926851afa0f1794236e7669847c6
```

- [ ] **Step 3: 本機以目標引擎實跑（CLAUDE.md 升版流程要求）**

```bash
python3 -m venv /tmp/pc-venv && /tmp/pc-venv/bin/pip -q install \
  git+https://github.com/hamanpaul/paulsha-conventions@58290153a400926851afa0f1794236e7669847c6
/tmp/pc-venv/bin/policy-check --repo ~/prj_pri/paulsha-hippo
```

Expected: exit 0、無 FAIL（WARN 可留待後續）。有 FAIL 先修再進下一步。

- [ ] **Step 4: CHANGELOG 記錄並 commit**

CHANGELOG.md 頂部加：

```markdown
## [Unreleased]
### Changed
- chore(policy): conventions 引擎 1.0.7 → 1.0.12（pin 5829015，與 paulshaclaw 對齊）
```

```bash
cd ~/prj_pri/paulsha-hippo
git add .paul-project.yml .github/workflows/policy-check.yml CHANGELOG.md
git commit -m "chore(policy): conventions 引擎升 1.0.12（pin 5829015）"
```

---

### Task 3: Python package 骨架 + `hippo --version`（TDD）

**Files:**
- Create: `~/prj_pri/paulsha-hippo/pyproject.toml`
- Create: `~/prj_pri/paulsha-hippo/paulsha_hippo/__init__.py`
- Create: `~/prj_pri/paulsha-hippo/paulsha_hippo/cli.py`
- Create: `~/prj_pri/paulsha-hippo/tests/test_cli.py`
- Modify: `~/prj_pri/paulsha-hippo/VERSION`（`0.0.0` → `0.1.0`）

**Interfaces:**
- Produces: `paulsha_hippo.cli.main(argv: list[str] | None) -> int`、`paulsha_hippo.__version__: str = "0.1.0"`、console script `hippo`。Task 4/5 的測試依賴本 task 的可安裝 package。

- [ ] **Step 1: 寫 failing test**

`tests/test_cli.py`：

```python
from paulsha_hippo import cli


def test_version_flag_prints_and_exits_zero(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "hippo 0.1.0"


def test_no_args_prints_usage_and_exits_nonzero(capsys):
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: 跑測試確認 fail**

```bash
cd ~/prj_pri/paulsha-hippo && python3 -m pytest tests/test_cli.py -q
```

Expected: `ModuleNotFoundError: No module named 'paulsha_hippo'`

- [ ] **Step 3: 最小實作**

`pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "paulsha-hippo"
version = "0.1.0"
description = "跨 LLM vendor 的經驗筆記基座：session 蒸餾、dream 整理、wakeup 回灌"
requires-python = ">=3.10"
license = { text = "MIT" }

[project.scripts]
hippo = "paulsha_hippo.cli:main"

[project.optional-dependencies]
test = ["pytest"]

[tool.setuptools.packages.find]
include = ["paulsha_hippo*"]
```

`paulsha_hippo/__init__.py`：

```python
"""paulsha-hippo：跨 LLM vendor 的經驗筆記基座（骨架期）。"""

__version__ = "0.1.0"
```

`paulsha_hippo/cli.py`：

```python
"""hippo CLI 入口（骨架期：僅 --version；命令樹於 code 遷入時擴充）。"""
import sys

from paulsha_hippo import __version__

_USAGE = "usage: hippo --version"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(f"hippo {__version__}")
        return 0
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

`VERSION` 內容改為：

```
0.1.0
```

- [ ] **Step 4: 安裝並確認測試綠**

```bash
cd ~/prj_pri/paulsha-hippo
python3 -m pip install -e ".[test]"
python3 -m pytest tests/ -q
hippo --version
```

Expected: `2 passed`；`hippo 0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml paulsha_hippo/ tests/test_cli.py VERSION
git commit -m "feat(cli): package 骨架與 hippo --version 入口（0.1.0）"
```

---

### Task 4: `paulsha_hippo.lib` 隔離護欄（TDD）

**Files:**
- Create: `~/prj_pri/paulsha-hippo/paulsha_hippo/lib/__init__.py`
- Create: `~/prj_pri/paulsha-hippo/tests/test_lib_isolation.py`

**Interfaces:**
- Consumes: Task 3 的 package 佈局
- Produces: CI 級護欄——`paulsha_hippo/lib/**` 內任何 `paulsha_hippo.*`（非 `paulsha_hippo.lib.*`）import 都使 pytest 失敗。遷入 lifecycle/idle/jsonl 時此測試自動生效。

- [ ] **Step 1: 寫 failing test（連同一個違規暫存檔驗證測試會抓）**

`tests/test_lib_isolation.py`：

```python
"""spec §3.2：lib 子 package 自足——禁止 import hippo 其他模組。"""
import ast
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parents[1] / "paulsha_hippo" / "lib"


def _violations() -> list[str]:
    found: list[str] = []
    for py in sorted(LIB_DIR.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.startswith("paulsha_hippo") and not name.startswith("paulsha_hippo.lib"):
                    found.append(f"{py.relative_to(LIB_DIR.parent.parent)}: {name}")
    return found


def test_lib_dir_exists():
    assert LIB_DIR.is_dir(), "paulsha_hippo/lib/ 不存在"


def test_lib_has_no_internal_hippo_imports():
    assert _violations() == []
```

- [ ] **Step 2: 跑測試確認 fail（lib 尚不存在）**

```bash
cd ~/prj_pri/paulsha-hippo && python3 -m pytest tests/test_lib_isolation.py -q
```

Expected: `test_lib_dir_exists` FAIL（`paulsha_hippo/lib/ 不存在`）

- [ ] **Step 3: 建 lib package**

`paulsha_hippo/lib/__init__.py`：

```python
"""自足共用件（lifecycle / idle / jsonl 遷入處）。

入會規則（spec §3.2）：兩個以上跨 repo 使用者、自足、盡量 stdlib-only。
本 package 禁止 import paulsha_hippo.lib.* 以外的 paulsha_hippo.*，
由 tests/test_lib_isolation.py 強制。
"""
```

- [ ] **Step 4: 確認綠 + 手動驗證護欄會咬人**

```bash
cd ~/prj_pri/paulsha-hippo && python3 -m pytest tests/test_lib_isolation.py -q
echo "import paulsha_hippo.cli" > paulsha_hippo/lib/_probe.py
python3 -m pytest tests/test_lib_isolation.py -q
rm paulsha_hippo/lib/_probe.py
```

Expected: 第一跑 `2 passed`；第二跑 `test_lib_has_no_internal_hippo_imports` FAIL 且訊息含 `_probe.py: paulsha_hippo.cli`；刪除 probe 後恢復。

- [ ] **Step 5: Commit**

```bash
git add paulsha_hippo/lib/__init__.py tests/test_lib_isolation.py
git commit -m "feat(lib): lib 子 package 與 import 隔離護欄"
```

---

### Task 5: deident gate day-1（TDD）

**Files:**
- Create: `~/prj_pri/paulsha-hippo/scripts/deident_scan.py`
- Create: `~/prj_pri/paulsha-hippo/tests/test_deident_scan.py`
- Create: `~/prj_pri/paulsha-hippo/.github/workflows/deident.yml`

**Interfaces:**
- Consumes: git tracked 檔案清單（`git ls-files`）
- Produces: `scan_text(text: str) -> list[str]`（回傳命中的 pattern 描述）；CLI `python3 scripts/deident_scan.py [--extra-patterns FILE]` exit 0=乾淨、1=有殘留。CI workflow 每 PR 跑。雇主／廠商詞彙走 `--extra-patterns`（機器本地檔，永不 commit）。

- [ ] **Step 1: 寫 failing test（fixture 字串用串接組裝，避免掃到測試檔自己）**

`tests/test_deident_scan.py`：

```python
from scripts.deident_scan import scan_text

HOME_PATH = "/ho" + "me/someuser/prj/x.py"
WIN_PATH = "C:\\\\Us" + "ers\\\\someone\\\\x"
WORK_MAIL = "dev@" + "corp.example-inc.com"


def test_flags_personal_absolute_paths():
    assert scan_text(f"see {HOME_PATH}") != []
    assert scan_text(f"see {WIN_PATH}") != []


def test_flags_non_public_email():
    assert scan_text(f"contact {WORK_MAIL}") != []


def test_allows_public_identities():
    ok = "haman.paul@gmail.com https://github.com/hamanpaul ~/.agents/memory"
    assert scan_text(ok) == []
```

- [ ] **Step 2: 跑測試確認 fail**

```bash
cd ~/prj_pri/paulsha-hippo && python3 -m pytest tests/test_deident_scan.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: 實作 scanner**

`scripts/__init__.py`：空檔。

`scripts/deident_scan.py`：

```python
"""deident gate day-1（R-21 / paulshaclaw#201 精神）：擋個人絕對路徑與非公開 email。

雇主／廠商詞彙屬敏感內容，一律放機器本地檔（--extra-patterns），永不 commit。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

_BUILTIN = [
    (re.compile(r"/home/[A-Za-z0-9_.-]+/"), "個人絕對路徑（/home/<user>/）"),
    (re.compile(r"[A-Za-z]:\\\\Users\\\\"), "個人絕對路徑（Windows Users）"),
    (
        re.compile(r"[A-Za-z0-9_.+-]+@(?!gmail\.com|users\.noreply\.github\.com|example\.com)[A-Za-z0-9-]+\.[A-Za-z0-9.-]+"),
        "非公開 email 網域",
    ),
]

_SELF = {"scripts/deident_scan.py", "tests/test_deident_scan.py"}


def scan_text(text: str, extra: list[tuple[re.Pattern, str]] | None = None) -> list[str]:
    hits = []
    for pat, desc in _BUILTIN + list(extra or []):
        if pat.search(text):
            hits.append(desc)
    return hits


def _load_extra(path: str | None) -> list[tuple[re.Pattern, str]]:
    if not path:
        return []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [(re.compile(re.escape(s.strip())), f"本地額外 pattern: {s.strip()[:2]}…") for s in lines if s.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--extra-patterns", default=None)
    args = p.parse_args(argv)
    extra = _load_extra(args.extra_patterns)
    files = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    dirty = 0
    for rel in files:
        if rel in _SELF:
            continue
        path = Path(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for desc in scan_text(text, extra):
            print(f"DEIDENT FAIL {rel}: {desc}", file=sys.stderr)
            dirty += 1
    return 1 if dirty else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 測試綠 + 對整個 repo 實跑**

```bash
cd ~/prj_pri/paulsha-hippo
python3 -m pytest tests/test_deident_scan.py -q
python3 scripts/deident_scan.py; echo "exit=$?"
```

Expected: `3 passed`；`exit=0`（template 內容乾淨）

- [ ] **Step 5: CI workflow**

`.github/workflows/deident.yml`：

```yaml
name: Deident Gate

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  deident:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Scan tracked files
        run: python3 scripts/deident_scan.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/ tests/test_deident_scan.py .github/workflows/deident.yml
git commit -m "feat(security): deident gate day-1（個人路徑/非公開 email 掃描 + CI）"
```

---

### Task 6: README 草稿（zh-tw，誠實狀態）

**Files:**
- Modify: `~/prj_pri/paulsha-hippo/README.md`（整檔覆寫）

**Interfaces:**
- Consumes: spec §7 結構、§5.6 quickstart
- Produces: 對外首頁；code 遷入前明標「骨架期」

- [ ] **Step 1: 覆寫 README.md**

```markdown
# paulsha-hippo 🦛

> 跨 LLM vendor 的經驗筆記基座——session 自動蒸餾成原子筆記，睡眠期（dream）整理，隔天喚醒（wakeup）回灌 context。
> 命名取自海馬迴（hippocampus）：大腦在睡眠時做記憶固化的器官。

**狀態：🧪 骨架期。** 程式碼遷入受 [paulshaclaw#125](https://github.com/hamanpaul/paulshaclaw/issues/125) 站穩閘約束；
設計見 [拆包執行設計 spec](https://github.com/hamanpaul/paulshaclaw/blob/main/docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md)。
下述安裝與使用流程為遷入後的目標介面（**尚未可用**）。

## Quickstart（規劃中）

    pipx install git+https://github.com/hamanpaul/paulsha-hippo
    hippo init                          # 三個問題：memory 資料夾、蒸餾 LLM、agent host
    hippo install hooks --host claude && hippo install service --enable
    hippo dream run --dry-run
    hippo wakeup

## 安裝（規劃中）

- 支援 host：claude / codex / copilot（session hooks 隨包出貨）
- 常駐：systemd user units 自動偵測；不可用時 `hippo dream supervise` 前景模式
- WSL 注意：`loginctl enable-linger` 才能開機自起

## 設定（規劃中）

單一檔 `~/.config/paulsha-hippo/config.yaml` + `HIPPO_*` env 覆寫；密鑰一律 `secret.env`（0600）。
蒸餾 LLM 三檔位：`claude-headless`（預設，零 key 管理）／`openai-compatible`（ollama、vLLM、內網端點）／`custom-argv`。

## 架構

pipeline：hooks ingress → raw → atomize 蒸餾 → ledger/moc → dream（清晨整理）→ wakeup（回灌）。
`paulsha_hippo/lib/`：自足共用件（lifecycle schema／idle／jsonl 原語），與 [paulshaclaw](https://github.com/hamanpaul/paulshaclaw) 共用。

## 家族

`paulshaclaw`（agent 框架）｜`paulsha-hippo`（本 repo，記憶基座）｜`paulsha-conventions`（policy 引擎）
```

- [ ] **Step 2: deident 實跑 + commit**

```bash
cd ~/prj_pri/paulsha-hippo
python3 scripts/deident_scan.py && git add README.md && git commit -m "docs(readme): 骨架期 README（定位/quickstart 目標介面/家族關係）"
```

Expected: exit 0 後 commit 成功

---

### Task 7: 開 PR、CI 全綠、merge

**Files:**
- 無新檔（分支 push + PR）

**Interfaces:**
- Consumes: Task 1–6 的 commits
- Produces: hippo repo main 上的完整骨架

- [ ] **Step 1: push + 開 PR**

```bash
cd ~/prj_pri/paulsha-hippo && git push -u origin feature/bootstrap
gh pr create --title "feat: repo 骨架（conventions 1.0.12 + CLI stub + lib 護欄 + deident gate）" --body "$(cat <<'EOF'
## 摘要

paulsha-hippo 出生骨架：conventions 引擎 1.0.12（pin 5829015）、package 0.1.0 與 hippo --version、
paulsha_hippo.lib import 隔離護欄、deident gate day-1、README 骨架期草稿。

依據：hamanpaul/paulshaclaw 之 openspec change memory-extraction-hippo（tasks §1 先行段）。

## 驗證

- pytest 5 passed（cli 2 + lib 隔離 2 + deident 3，扣重疊）
- 本機 policy-check（引擎 1.0.12）零 FAIL
- scripts/deident_scan.py exit 0

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL

- [ ] **Step 2: 等 CI（Policy Check / Tests / Deident Gate）全綠後 merge**

```bash
cd ~/prj_pri/paulsha-hippo && gh pr checks --watch && gh pr merge --squash --delete-branch
```

Expected: 三個 check 全 pass；merge 成功

---

### Task 8: 主 repo #125 更名註記

**Files:**
- 無檔案變更（GitHub issue comment）

**Interfaces:**
- Consumes: hippo repo URL、spec / change 路徑
- Produces: #125 上的權威更名記錄（雙機協調：不改分支正在寫的檔）

- [ ] **Step 1: 留言**

```bash
gh issue comment 125 --repo hamanpaul/paulshaclaw --body "$(cat <<'EOF'
📛 工作名更名：Phase 1 拆包目標 repo 由 `paulsha-memory` 定名為 **`paulsha-hippo`**（海馬迴＝睡眠期記憶固化，對應 dream service 隱喻）。

- 執行設計 spec：`docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md`（PR #202，含 Codex 對抗審查四項修正）
- openspec change：`openspec/changes/memory-extraction-hippo/`
- 骨架 repo：https://github.com/hamanpaul/paulsha-hippo（private，先行段已立；code 遷移仍受站穩閘 G1–G5 約束）
- lifecycle 處置維持「先二後三」（本 change 即傘狀件要求的動工前重新確認）

`feature/p0-p3-specs` 分支上的 specs 使用舊工作名之處，待該分支 merge 後另出 docs 對齊 PR，不動開發中檔案。
EOF
)"
```

Expected: comment URL

---

## Self-Review 記錄

- **Spec 覆蓋**：本計劃對應 openspec tasks §1（1.1 repo=Task 1-2、1.2 CI 四道=Task 2/5 + template 出廠 tests/policy（lib import-lint 以 pytest 實作併入 Tests check）、1.3 README=Task 6、1.4 #125 註記=Task 8）。§2–§5 屬閘後計劃，明示不在本計劃範圍。
- **佔位符**：無 TBD/TODO；所有步驟含完整程式碼與預期輸出。
- **型別一致**：`cli.main(argv) -> int` 與 `scan_text(text, extra) -> list[str]` 在各 task 引用一致；`hippo 0.1.0` 字串與 `__version__`、pyproject、VERSION 三處對齊。
