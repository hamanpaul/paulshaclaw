# paulsha-hippo Repo Bootstrap 實作計劃（#125 Phase 1 先行段）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `hamanpaul/paulsha-hippo` repo 骨架（template + conventions 1.0.12 + `tier: shareable`（R-21 deident）+ CLI stub + lib 隔離護欄 + README 草稿），不搬任何 memory 程式碼。

**Architecture:** 依 `docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md`。本計劃只涵蓋 openspec change `memory-extraction-hippo` tasks.md 的 §1（先行，不必等閘）；§3 hippo 遷入與 §4 主 repo 遷移受站穩閘約束，閘清後各出獨立計劃。

**Tech Stack:** Python 3.10+（CI 3.12）、pytest、gh CLI、paulsha-conventions 1.0.12（reusable workflow）、GitHub rulesets。

## Global Constraints

- 新 repo 首發為 **private**；轉 public 前必過 deident sanitize（#201 / R-21）。
- deident 由 conventions **R-21 承接**（P0-1「上游為正主」，#211）：`.paul-project.yml` 宣告 `tier: shareable`，markers 基線在引擎套件內、不進 repo；**不自製 scanner**。
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
tier: shareable
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
註：`tier: shareable` 使 **R-21 機密掃描**同時生效——這就是 deident gate day-1 的實作（引擎內建 markers 基線，雇主／廠商詞彙不進 repo；如需 repo 端擴充用 `secret_scan.markers`，extend-only）。

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
- Create: `~/prj_pri/paulsha-hippo/tests/test_version_consistency.py`
- Modify: `~/prj_pri/paulsha-hippo/VERSION`（`0.0.0` → `0.1.0`）

**Interfaces:**
- Produces: `paulsha_hippo.cli.main(argv: list[str] | None) -> int`、`paulsha_hippo.__version__: str = "0.1.0"`、console script `hippo`。Task 4 的測試依賴本 task 的可安裝 package。版號一致性測試鏡射主 repo #204 的 R-07 對齊慣例。

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

`tests/test_version_consistency.py`（R-07 對齊，鏡射主 repo #204 慣例）：

```python
import re
from pathlib import Path

import paulsha_hippo

ROOT = Path(__file__).resolve().parents[1]


def test_version_file_matches_package():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == paulsha_hippo.__version__


def test_pyproject_matches_package():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', text, flags=re.M)
    assert m and m.group(1) == paulsha_hippo.__version__
```

- [ ] **Step 2: 跑測試確認 fail**

```bash
cd ~/prj_pri/paulsha-hippo && python3 -m pytest tests/ -q
```

Expected: `ModuleNotFoundError: No module named 'paulsha_hippo'`（兩檔皆 fail）

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

Expected: `4 passed`；`hippo 0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml paulsha_hippo/ tests/test_cli.py tests/test_version_consistency.py VERSION
git commit -m "feat(cli): package 骨架、hippo --version 入口與版號一致性測試（0.1.0）"
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

### Task 5: README 草稿（zh-tw，誠實狀態）

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

- [ ] **Step 2: Commit**

```bash
cd ~/prj_pri/paulsha-hippo
git add README.md && git commit -m "docs(readme): 骨架期 README（定位/quickstart 目標介面/家族關係）"
```

Expected: commit 成功（README 的機密掃描由 Task 6 CI 之 policy-check R-21 承接）

---

### Task 6: 開 PR、CI 全綠、merge

**Files:**
- 無新檔（分支 push + PR）

**Interfaces:**
- Consumes: Task 1–5 的 commits
- Produces: hippo repo main 上的完整骨架

- [ ] **Step 1: push + 開 PR**

```bash
cd ~/prj_pri/paulsha-hippo && git push -u origin feature/bootstrap
gh pr create --title "feat: repo 骨架（conventions 1.0.12 + tier shareable + CLI stub + lib 護欄）" --body "$(cat <<'EOF'
## 摘要

paulsha-hippo 出生骨架：conventions 引擎 1.0.12（pin 5829015）+ `tier: shareable`（R-21 機密掃描
即 deident gate day-1）、package 0.1.0 與 hippo --version、版號一致性測試（R-07 對齊）、
paulsha_hippo.lib import 隔離護欄、README 骨架期草稿。

依據：hamanpaul/paulshaclaw 之 openspec change memory-extraction-hippo（tasks §1 先行段）。

## 驗證

- pytest 6 passed（cli 2 + 版號一致 2 + lib 隔離 2）
- 本機 policy-check（引擎 1.0.12、含 R-21）零 FAIL

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL

- [ ] **Step 2: 等 CI（Policy Check / Tests）全綠後 merge**

```bash
cd ~/prj_pri/paulsha-hippo && gh pr checks --watch && gh pr merge --squash --delete-branch
```

Expected: 兩個 check 全 pass；merge 成功

---

### Task 7: 主 repo #125 更名註記

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

舊工作名 `paulsha-memory` 散見已 merge 的歷史 specs／archives（查證：無活文件引用），屬 R-22 陳年 advisory，不做 rename 沖刷；本留言為權威更名記錄。
EOF
)"
```

Expected: comment URL

---

## Self-Review 記錄

- **Spec 覆蓋**：本計劃對應 openspec tasks §1（1.1 repo=Task 1-2、1.2 CI 四道=Task 2 + template 出廠 tests/policy——lib import-lint 以 pytest 併入 Tests check、deident 以 R-21 `tier: shareable` 併入 Policy Check、1.3 README=Task 5、1.4 #125 註記=Task 7）。§2–§5 屬閘後計劃，明示不在本計劃範圍。
- **佔位符**：無 TBD/TODO；所有步驟含完整程式碼與預期輸出。
- **型別一致**：`cli.main(argv) -> int` 在各 task 引用一致；`hippo 0.1.0` 字串與 `__version__`、pyproject、VERSION 三處對齊（並由 test_version_consistency 固化）。
- **2026-07-06 重評（p0-p3 merge 後）**：刪自製 deident scanner（R-21 為正主，#211）；補版號一致性測試（鏡射 #204）；#125 留言措辭更新（分支已 merge、舊名屬陳年 advisory）。閘門進度：G4 ✅、G1 code 已接線、p1 ⅔、P2 ½（#91 open）、G5 未動——閘後兩段維持等待。
