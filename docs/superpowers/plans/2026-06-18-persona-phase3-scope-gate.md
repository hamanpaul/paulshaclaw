# Persona Phase 3 — 自建 persona-scope CI 硬後盾（shadow 形狀）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 persona 派工護欄 ②（PR diff gate）接成 GitHub Actions 的 **shadow 硬後盾**：一支自我封裝的 CI runner `paulshaclaw/persona/scope_ci.py` ＋ 一個 `.github/workflows/persona-scope.yml`。本階段**只到 shadow**——workflow 恆 exit 0、**non-blocking**、**非 required status check**、不動 branch protection。enforce 翻牌（shadow→enforce）與自管豁免 label `policy-exempt:persona-scope` 為**文件化的未來手動步驟**，本 plan 不啟用。

**Architecture:** 全部 reuse Phase 1 的 `gate.py` / `handoff.py`，**不重寫 scope 判定邏輯**：
- `gate.compute_changed_paths(base, head, repo=None)` — `git diff --name-only base...head`，非零 returncode raise `RuntimeError`（fail-closed）。
- `gate.load_manifest_ok(role, manifest_path, catalog=None)` — 讀驗 manifest，fail-closed → False。
- `gate.build_verdict(*, role, changed_paths, manifest_ok, catalog=None)` — 算 `{role, changed_paths, violations, handoff_ok, ok}`。
- `handoff.read_manifest(path, catalog=None)` — fail-closed 讀回 payload（取 `from_role`）。
- `loader.load_catalog()` — catalog 來源。

`scope_ci` 採「純函式 + 薄 `main(argv, env)`」：`resolve_base` / `resolve_head` / `find_latest_manifest` 可單測；`main` 解析 env、探測 manifest、印 JSON、回 exit code。`env` 預設 `os.environ` 但可注入 → 測試完全不碰真 GitHub 環境。

**核心安全約束（違反即破壞未來所有 PR，視為 blocking）:**
1. **shadow / non-blocking**：`main` 恆 `return 0`；workflow 恆 exit 0；**MUST NOT** 設為 required status check（無 branch-protection 變更）。
2. **無 manifest 乾淨跳過**：找不到 `runtime/handoff/*.json` → 印 `skipped (shadow)` + return 0，**絕不報錯**。這是常態（本 Phase 3 PR 自身、其他 repo PR 皆無 manifest），**必須照樣 pass**。
3. **additive only**：**MUST NOT** 修改 `.github/workflows/tests.yml` 或 `.github/workflows/policy-check.yml`。
4. **enforce / required / label 僅文件化**：寫進 openspec proposal/design 作為未來手動步驟，本 plan 不啟用任何強制。

**Tech Stack:** Python 3.12、`unittest`、stdlib（`argparse`、`glob`、`json`、`os`、`pathlib`、`tempfile`、`io`、`contextlib`）。無新增外部依賴（`PyYAML` 已在 `requirements-stage9.txt`、`git` 為既有前提）。

**Out of scope（後續/文件化）:** enforce 翻牌；required status check 與 branch protection；豁免 label 判讀；② 角色不變式（reviewer diff 不可含 code、builder 須帶測試）；修改既有 `gate.py`/`handoff.py`/`loader.py`。

---

## File Structure

- Commit-only（Task 1）：`openspec/changes/persona-phase3-scope-gate/**`、本 plan
- Create: `tests/test_persona_phase3_scope_ci.py` — 三組 RED 測試（無 manifest／in-scope／out-of-scope + diff 失敗）
- Create: `paulshaclaw/persona/scope_ci.py` — 純函式 + `main(argv, env)` CI runner
- Create: `.github/workflows/persona-scope.yml` — shadow、non-blocking、非 required
- Modify: `paulshaclaw/persona/__init__.py` — 匯出 `scope_ci`
- **DO NOT MODIFY:** `.github/workflows/tests.yml`、`.github/workflows/policy-check.yml`

**全套件測試指令（CI 同款）：** `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
**既知環境失敗（忽略）：** `tests/test_stage11_operator_cockpit.py` 的 2 筆（`query_one` / textual 未裝於 system python3）。其餘任何失敗皆為真。

---

### Task 1: 提交規劃 artifacts

**Files:**
- Commit: `openspec/changes/persona-phase3-scope-gate/`（proposal/design/specs/tasks/.openspec.yaml）、本 plan

- [ ] **Step 1: 確認分支與待提交檔**

Run: `git branch --show-current && git status --short`
Expected: 分支 `feature/persona-phase3-scope-gate`；列出未追蹤的 `openspec/changes/persona-phase3-scope-gate/` 與本 plan。

- [ ] **Step 2: openspec 驗證**

Run: `openspec validate persona-phase3-scope-gate --strict`
Expected: `Change 'persona-phase3-scope-gate' is valid`。

- [ ] **Step 3: 提交（本 step 由 controller 在本任務外已執行；若重跑流程才需）**

> 註：本計畫的 openspec change + plan 已於 `docs(persona): Phase 3 openspec change + plan` 一次 docs commit 提交。Task 1 在實作 session 中僅需確認 artifacts 在位、validate 通過，**不重複提交**。

---

### Task 2: scope_ci.py（CI runner，shadow 恆放行）— TDD

**Files:**
- Test: `tests/test_persona_phase3_scope_ci.py`（新增三組測試 + helper）
- Create: `paulshaclaw/persona/scope_ci.py`

- [ ] **Step 1: 寫失敗測試（RED）**

建立 `tests/test_persona_phase3_scope_ci.py`：

```python
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _valid_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_role": "builder",
        "to_role": "reviewer",
        "phase": "review",
        "gate_status": "passed",
        "slice_id": "persona-phase3-scope-gate",
        "summary": "phase3 scope ci shadow",
        "artifact_refs": ["feature/persona-phase3-scope-gate"],
        "created_at": "2026-06-18T00:00:00+08:00",
        "base": "main",
        "head": "feature/persona-phase3-scope-gate",
    }
    payload.update(overrides)
    return payload


def _write_manifest(repo_root: Path, **overrides: object) -> Path:
    from paulshaclaw.persona import handoff

    path = repo_root / "runtime" / "handoff" / "persona-phase3-scope-gate.json"
    handoff.write_manifest(path, _valid_manifest(**overrides))
    return path


def _run(repo_root: Path, env: dict[str, str]) -> tuple[int, dict[str, object]]:
    """跑 scope_ci.main 並擷取 stdout JSON。"""
    from paulshaclaw.persona import scope_ci

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = scope_ci.main(argv=["--repo", str(repo_root)], env=env)
    out = buf.getvalue().strip().splitlines()
    payload = json.loads(out[-1]) if out else {}
    return code, payload


class NoManifestTests(unittest.TestCase):
    def test_empty_handoff_dir_skips_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "runtime" / "handoff").mkdir(parents=True)  # 空目錄
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main"})
            self.assertEqual(code, 0)
            self.assertTrue(payload.get("skipped"))
            self.assertIn("skipped", json.dumps(payload))

    def test_no_runtime_dir_at_all_skips_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)  # 連 runtime/ 都沒有 → 仍須乾淨跳過、不報錯
            code, payload = _run(repo, {})
            self.assertEqual(code, 0)
            self.assertTrue(payload.get("skipped"))


class InScopeShadowTests(unittest.TestCase):
    def _patch_diff(self, paths: list[str]):
        from paulshaclaw.persona import gate

        original = gate.compute_changed_paths
        gate.compute_changed_paths = lambda base, head, repo=None: list(paths)
        self.addCleanup(setattr, gate, "compute_changed_paths", original)

    def test_in_scope_diff_ok_and_exit_zero(self) -> None:
        self._patch_diff(["paulshaclaw/persona/scope_ci.py", "tests/test_x.py"])
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _write_manifest(repo)  # from_role=builder
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main", "GITHUB_SHA": "deadbeef"})
            self.assertEqual(code, 0)
            self.assertEqual(payload["role"], "builder")
            self.assertEqual(payload["violations"], [])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "shadow")
            self.assertEqual(payload["base"], "origin/main")
            self.assertEqual(payload["head"], "deadbeef")


class OutOfScopeShadowTests(unittest.TestCase):
    def _patch_diff(self, paths: list[str]):
        from paulshaclaw.persona import gate

        original = gate.compute_changed_paths
        gate.compute_changed_paths = lambda base, head, repo=None: list(paths)
        self.addCleanup(setattr, gate, "compute_changed_paths", original)

    def test_out_of_scope_diff_violations_but_still_exit_zero(self) -> None:
        # builder 不可寫 docs/** → 越界
        self._patch_diff(["paulshaclaw/persona/scope_ci.py", "docs/secret.md"])
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _write_manifest(repo)  # from_role=builder
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main"})
            self.assertEqual(code, 0)  # shadow 恆 0，即使越界
            self.assertFalse(payload["ok"])
            offending = [v["path"] for v in payload["violations"]]
            self.assertIn("docs/secret.md", offending)
            for v in payload["violations"]:
                self.assertTrue(v["reason"])  # 帶可審計原因

    def test_diff_failure_fail_closed_but_shadow_exit_zero(self) -> None:
        from paulshaclaw.persona import gate

        def _raise(base, head, repo=None):
            raise RuntimeError("git diff 失敗（fail-closed）: no merge base")

        original = gate.compute_changed_paths
        gate.compute_changed_paths = _raise
        self.addCleanup(setattr, gate, "compute_changed_paths", original)

        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _write_manifest(repo)
            code, payload = _run(repo, {"GITHUB_BASE_REF": "main"})
            self.assertEqual(code, 0)  # shadow 仍放行
            self.assertIn("diff_error", payload)
            self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED 為預期原因**

Run: `python -m pytest tests/test_persona_phase3_scope_ci.py -q`
Expected: RED，原因為 `ModuleNotFoundError: No module named 'paulshaclaw.persona.scope_ci'`（缺模組）。捕捉輸出為證據。

- [ ] **Step 3: 實作 scope_ci.py（GREEN）**

建立 `paulshaclaw/persona/scope_ci.py`：

```python
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

from . import gate, handoff
from .loader import load_catalog

HANDOFF_GLOB = "runtime/handoff/*.json"


def resolve_base(env: Mapping[str, str]) -> str:
    """PR base ref：origin/<GITHUB_BASE_REF>（缺省 main）。

    對齊 actions/checkout@v4 + fetch-depth:0 後 base 分支以 remote-tracking
    ref（origin/<branch>）存在的事實。
    """
    base_ref = env.get("GITHUB_BASE_REF") or "main"
    return f"origin/{base_ref}"


def resolve_head(env: Mapping[str, str]) -> str:
    """PR head：GITHUB_SHA（缺省 HEAD）。"""
    return env.get("GITHUB_SHA") or "HEAD"


def find_latest_manifest(repo_root: str | Path | None = None) -> Path | None:
    """找 runtime/handoff/*.json 中 mtime 最新者；無則 None（不報錯）。"""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    candidates = [Path(p) for p in glob.glob(str(root / HANDOFF_GLOB))]
    files = [p for p in candidates if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """Shadow persona-scope CI runner：恆 return 0（observe/annotate-only）。

    無 manifest（常態）→ 印 skipped 通知並放行。
    有 manifest → reuse gate verdict 邏輯、印 JSON，shadow 仍恆放行。
    """
    env = os.environ if env is None else env

    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.persona.scope_ci")
    parser.add_argument("--repo", default=None, help="repo root（預設 cwd；測試可注入 temp dir）")
    args = parser.parse_args(argv)

    repo_root = args.repo
    manifest = find_latest_manifest(repo_root)
    if manifest is None:
        print(
            json.dumps(
                {"mode": "shadow", "skipped": True,
                 "notice": "no manifest, skipped (shadow)"},
                ensure_ascii=False,
            )
        )
        return 0  # 無 manifest 為常態 → 乾淨放行

    base = resolve_base(env)
    head = resolve_head(env)
    catalog = load_catalog()

    # manifest 存在但壞掉 → 視為「存在但不可信」：印 verdict（ok=false）、shadow 放行。
    try:
        payload = handoff.read_manifest(manifest, catalog)
        from_role = str(payload.get("from_role", ""))
        manifest_error: str | None = None
    except (FileNotFoundError, ValueError) as exc:
        from_role = ""
        manifest_error = str(exc)

    try:
        changed_paths = gate.compute_changed_paths(base, head, repo=repo_root)
        diff_error: str | None = None
    except RuntimeError as exc:  # fail-closed：取 diff 失敗 → 標記但 shadow 不擋
        changed_paths = []
        diff_error = str(exc)

    manifest_ok = gate.load_manifest_ok(from_role, manifest, catalog)
    verdict = gate.build_verdict(
        role=from_role,
        changed_paths=changed_paths,
        manifest_ok=manifest_ok,
        catalog=catalog,
    )
    verdict["mode"] = "shadow"
    verdict["manifest"] = str(manifest)
    verdict["base"] = base
    verdict["head"] = head
    if manifest_error is not None:
        verdict["manifest_error"] = manifest_error
        verdict["ok"] = False
    if diff_error is not None:
        verdict["diff_error"] = diff_error
        verdict["ok"] = False

    print(json.dumps(verdict, ensure_ascii=False))
    return 0  # shadow：恆放行，僅觀測/annotate


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

> 設計對應：`resolve_base`/`resolve_head`=D1；`find_latest_manifest`+ None 分支=D2（無 manifest 乾淨跳過）；reuse `gate.build_verdict`=D3（不重寫 scope）；`diff_error`/`manifest_error` 標記但恆 return 0=D4（fail-closed but shadow 放行）。

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase3_scope_ci.py -q`
Expected: 5 passed。

---

### Task 3: persona-scope.yml（shadow、non-blocking、非 required）

**Files:**
- Create: `.github/workflows/persona-scope.yml`
- **DO NOT MODIFY:** `.github/workflows/tests.yml`、`.github/workflows/policy-check.yml`

- [ ] **Step 1: 建立 workflow**

建立 `.github/workflows/persona-scope.yml`：

```yaml
name: Persona Scope (shadow)

# Shadow / non-blocking persona-scope guardrail（設計 §8 / §11 Phase 3）。
# 此 workflow 恆 exit 0（observe/annotate-only），MUST NOT 被設為 required status check。
# enforce 翻牌（shadow→enforce）與 policy-exempt:persona-scope label 為文件化的未來手動步驟，
# 見 openspec/changes/persona-phase3-scope-gate/{proposal,design}.md。

on:
  pull_request:

permissions:
  contents: read

jobs:
  persona-scope:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pytest -r requirements-stage9.txt

      - name: Run persona-scope (shadow, always exit 0)
        run: python -m paulshaclaw.persona.scope_ci
```

> 對齊 house style（`tests.yml`）：`actions/checkout@v4`、`actions/setup-python@v5`、`python-version: "3.12"`、`permissions: contents: read`、`pip install --upgrade pip` 起手。`fetch-depth: 0` 為 gate 取 base...head 共同祖先所需。`pip install pytest -r requirements-stage9.txt`：`PyYAML` 在 stage9 requirements、是 `load_catalog()` 載 `personas.yaml` 的硬需求（D6）。

- [ ] **Step 2: 自我審查硬安全約束**

Run: `python -c "import yaml; d=yaml.safe_load(open('.github/workflows/persona-scope.yml')); assert 'pull_request' in (d.get(True) or d.get('on')); assert list(d['jobs'])==['persona-scope']; print('on=pull_request OK; job OK')"`
Expected: 印 OK。並人工確認：
  - workflow 跑 `python -m paulshaclaw.persona.scope_ci`（runner 恆 exit 0）。
  - **未**含 `if: ... required`、**未**有任何 branch-protection 設定（workflow 無法自設 required，但仍人工確認文件未誤導）。
  - `git status --short .github/workflows/` 顯示**只新增** `persona-scope.yml`，`tests.yml`/`policy-check.yml` **未被改**。

Run: `git diff --stat -- .github/workflows/tests.yml .github/workflows/policy-check.yml`
Expected: 空輸出（兩檔零變更）。

---

### Task 4: 匯出 + 不回歸

**Files:**
- Modify: `paulshaclaw/persona/__init__.py`

- [ ] **Step 1: 匯出新模組**

把 `paulshaclaw/persona/__init__.py` 改為（在既有匯入加入 `scope_ci`）：

```python
"""Stage4 persona contract and guardrail primitives."""

from . import context, contract, gate, guardrail, handoff, render, scope_ci, shadow

__all__ = [
    "contract",
    "guardrail",
    "context",
    "shadow",
    "handoff",
    "render",
    "gate",
    "scope_ci",
]
```

- [ ] **Step 2: 既有 persona 測試針對性確認**

Run: `python -m pytest tests/test_stage4_persona_contract.py tests/test_persona_config_loader.py tests/test_persona_phase1_shadow_gate.py tests/test_persona_phase2_coordinator_cli.py -q`
Expected: 全綠（Phase 3 純 reuse gate，不改既有判定邏輯，故行為不變）。

- [ ] **Step 3: 全套件不回歸**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠，**唯二允許失敗** 為 `tests/test_stage11_operator_cockpit.py` 的 textual/`query_one` 兩筆既知環境失敗；其餘任何失敗皆為真，須回到對應 Task 修。

---

### Task 5: 驗證（設計 §11 Phase 3 獨立驗收 — shadow 部分）

- [ ] **Step 1: openspec 驗證**

Run: `openspec validate persona-phase3-scope-gate --strict`
Expected: `Change 'persona-phase3-scope-gate' is valid`。

- [ ] **Step 2: 本機模擬「無 manifest」PR（最關鍵安全路徑）**

Run:
```bash
python -m paulshaclaw.persona.scope_ci
echo "no-manifest exit=$?"
```
Expected: 印 `{"mode": "shadow", "skipped": true, "notice": "no manifest, skipped (shadow)"}`，**exit 0**（本分支 `runtime/handoff/` 無 manifest → 必須安靜放行；這正是「絕大多數 PR 無 manifest 仍 pass」的獨立驗收）。

- [ ] **Step 3: 本機模擬「有 manifest 且越界」PR（shadow 恆放行）**

Run:
```bash
python - <<'PY'
import tempfile, io, json
from contextlib import redirect_stdout
from pathlib import Path
from paulshaclaw.persona import handoff, scope_ci, gate

gate.compute_changed_paths = lambda base, head, repo=None: ["docs/secret.md", "paulshaclaw/x.py"]
with tempfile.TemporaryDirectory() as d:
    repo = Path(d)
    handoff.write_manifest(repo / "runtime" / "handoff" / "s.json", {
        "from_role": "builder", "to_role": "reviewer", "phase": "review",
        "gate_status": "passed", "slice_id": "s", "summary": "x",
        "artifact_refs": ["b"], "created_at": "2026-06-18T00:00:00+08:00"})
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = scope_ci.main(argv=["--repo", str(repo)], env={"GITHUB_BASE_REF": "main"})
    v = json.loads(buf.getvalue().strip())
    print("exit:", rc, "| ok:", v["ok"], "| violations:", [x["path"] for x in v["violations"]])
    assert rc == 0, "shadow MUST exit 0 even on violation"
    print("PASS")
PY
```
Expected: `exit: 0 | ok: False | violations: ['docs/secret.md']` 後印 `PASS`（越界但 shadow 恆 exit 0）。

- [ ] **Step 4: 確認 enforce / required / label 僅文件化、本 change 未啟用**

Run: `grep -n "enforce\|required\|policy-exempt:persona-scope" openspec/changes/persona-phase3-scope-gate/proposal.md openspec/changes/persona-phase3-scope-gate/design.md`
Expected: 命中於「文件化未來手動步驟」段落。並人工確認：
  - `scope_ci.py` **無** `--enforce` 旗標、`main` 無條件 `return 0`。
  - `persona-scope.yml` **未**設為 required、**未**動 branch protection。
  - `.github/workflows/tests.yml`、`.github/workflows/policy-check.yml` **零變更**。

---

## Done When

- [ ] `scope_ci.py` 就位且 `__init__` 已匯出 `scope_ci`。
- [ ] `.github/workflows/persona-scope.yml` 就位：`on: pull_request`、`fetch-depth: 0`、跑 `python -m paulshaclaw.persona.scope_ci`、**非 required、non-blocking**。
- [ ] `.github/workflows/tests.yml`、`.github/workflows/policy-check.yml` **未被修改**（additive only）。
- [ ] `tests/test_persona_phase3_scope_ci.py` 五個測試全綠（含無 manifest 跳過、in-scope ok、out-of-scope shadow 仍 exit 0、diff 失敗 fail-closed 仍 exit 0）。
- [ ] 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（除 2 個既知 stage11 textual 失敗）。
- [ ] `openspec validate persona-phase3-scope-gate --strict` 通過。
- [ ] 本機驗收：無 manifest → `skipped (shadow)` + exit 0；有 manifest 越界 → verdict 印出但 shadow exit 0。
- [ ] enforce 翻牌 + required check + `policy-exempt:persona-scope` label 皆**僅文件化於 proposal/design**，本 change 未啟用任何強制、未改 branch protection。
- [ ] 全程 local commit、**不 push/不開 PR/不 merge**（由 controller 在 gating 後處理）。
```
