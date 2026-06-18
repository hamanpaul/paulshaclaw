# Persona Phase 1 — Shadow 護欄（handoff manifest + ① render + ② diff-gate CLI）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 persona 三個強制點（①派工 contract render、②PR diff gate、③merge 前終檢的讀寫載體）的 **shadow 觀測形狀** 接出，不引入 runtime 強制。交付三模組：`handoff.py`（manifest 讀寫，read fail-closed）、`render.py`（contract → prompt 前言）、`gate.py`（`git diff` 逐檔 `evaluate_filesystem` + 驗 manifest 的薄 CLI，預設 shadow 恆 exit 0、`--enforce` 違規 exit 1）。

**Architecture:** 全部 reuse 既有 Phase 0 API，不重寫判定邏輯：
- `contract.validate_handoff_message(payload, catalog=None)` — manifest 驗證（read fail-closed 的信任邊界）。
- `context.build_persona_context(role=, catalog=, overlay=)` — render 的契約來源（未知 role 已 raise `ValueError`）。
- `guardrail.PersonaGuardrail(catalog).evaluate_filesystem(role=, path=)` — gate 逐檔判定。
- `loader.load_catalog()` — gate 的 catalog 來源。

gate 採「純函式 + 薄 `main(argv)`」：`compute_changed_paths` / `evaluate_diff` / `load_manifest_ok` / `build_verdict` 可單測，`main` 只解析參數、印 JSON、回 exit code。shadow（預設）恆 return 0；`--enforce` 時 `0 if ok else 1`。

**Tech Stack:** Python 3.12、`unittest`、stdlib（`json`、`subprocess`、`argparse`、`pathlib`、`tempfile`）。無新增外部依賴。

**Out of scope（後續階段）:** ② 的角色不變式（reviewer diff 不可含 code、builder 須帶測試）；coordinator dispatch（Phase 2）；`persona-scope.yml` CI（Phase 3）；fan-out（Phase 4）；真正翻 enforce 的決策。

---

## File Structure

- Commit-only（Task 1）：`openspec/changes/persona-phase1-shadow-gate/**`、本 plan
- Create: `tests/test_persona_phase1_shadow_gate.py` — 四組 RED 測試
- Create: `paulshaclaw/persona/handoff.py` — `write_manifest` / `read_manifest`
- Create: `paulshaclaw/persona/render.py` — `render_contract_prompt`
- Create: `paulshaclaw/persona/gate.py` — 純函式 + `main(argv)` CLI
- Modify: `paulshaclaw/persona/__init__.py` — 匯出 `handoff`、`render`、`gate`

**全套件測試指令（CI 同款）：** `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
**既知環境失敗（忽略）：** `tests/test_stage11_operator_cockpit.py` 2 筆（`query_one` / textual 未裝於 system python3）。其餘任何失敗皆為真。

---

### Task 1: 提交規劃 artifacts

**Files:**
- Commit: `openspec/changes/persona-phase1-shadow-gate/`（proposal/design/specs/tasks/.openspec.yaml）、本 plan

- [ ] **Step 1: 確認分支與待提交檔**

Run: `git branch --show-current && git status --short`
Expected: 分支 `feature/persona-phase1-shadow-gate`；列出未追蹤的 `openspec/changes/persona-phase1-shadow-gate/` 與本 plan。

- [ ] **Step 2: openspec 驗證**

Run: `openspec validate persona-phase1-shadow-gate --strict`
Expected: `Change 'persona-phase1-shadow-gate' is valid`。

- [ ] **Step 3: 提交（本 step 由 controller 在本任務外已執行；若重跑流程才需）**

> 註：本計畫的 openspec change + plan 已於 `docs(persona): Phase 1 openspec change + plan` 一次 docs commit 提交。Task 1 在實作 session 中僅需確認 artifacts 在位、validate 通過，**不重複提交**。

---

### Task 2: handoff.py（manifest 讀寫，read fail-closed）— TDD

**Files:**
- Test: `tests/test_persona_phase1_shadow_gate.py`（新增 `HandoffManifestTests`）
- Create: `paulshaclaw/persona/handoff.py`

- [ ] **Step 1: 寫失敗測試（RED）**

建立 `tests/test_persona_phase1_shadow_gate.py`，先放共用 import 與 `HandoffManifestTests`：

```python
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def _valid_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_role": "builder",
        "to_role": "reviewer",
        "phase": "review",
        "gate_status": "passed",
        "slice_id": "persona-phase1-shadow-gate",
        "summary": "phase1 shadow gate building blocks",
        "artifact_refs": ["feature/persona-phase1-shadow-gate"],
        "created_at": "2026-06-18T00:00:00+08:00",
        "base": "main",
        "head": "feature/persona-phase1-shadow-gate",
    }
    payload.update(overrides)
    return payload


class HandoffManifestTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        from paulshaclaw.persona import handoff

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "runtime" / "handoff" / "persona-phase1-shadow-gate.json"
            payload = _valid_manifest()
            handoff.write_manifest(path, payload)
            self.assertTrue(path.is_file())
            loaded = handoff.read_manifest(path)
            self.assertEqual(loaded, payload)

    def test_write_creates_parent_dirs(self) -> None:
        from paulshaclaw.persona import handoff

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a" / "b" / "c.json"
            handoff.write_manifest(path, _valid_manifest())
            self.assertTrue(path.is_file())

    def test_invalid_manifest_raises(self) -> None:
        from paulshaclaw.persona import handoff

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            # 缺 created_at 且 gate_status 非法 → validate_handoff_message 不過
            bad = _valid_manifest()
            del bad["created_at"]
            bad["gate_status"] = "bogus"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                handoff.read_manifest(path)

    def test_missing_file_fails_closed(self) -> None:
        from paulshaclaw.persona import handoff

        with self.assertRaises(Exception) as ctx:
            handoff.read_manifest("/nonexistent/handoff/x.json")
        # fail-closed：FileNotFoundError 或 ValueError 皆可，重點是 raise 而非回傳空
        self.assertIsInstance(ctx.exception, (FileNotFoundError, ValueError))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED 為預期原因**

Run: `python -m pytest tests/test_persona_phase1_shadow_gate.py::HandoffManifestTests -q`
Expected: RED，原因為 `ModuleNotFoundError: No module named 'paulshaclaw.persona.handoff'`（缺模組）。捕捉輸出為證據。

- [ ] **Step 3: 實作 handoff.py（GREEN）**

建立 `paulshaclaw/persona/handoff.py`：

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from . import contract


def write_manifest(path: str | Path, payload: Mapping[str, object]) -> Path:
    """序列化 handoff manifest 至 path，確保父目錄存在。

    寫入端不驗證（責任在呼叫者）；read 端為 fail-closed 信任邊界。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def read_manifest(
    path: str | Path,
    catalog: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """讀回 handoff manifest 並 fail-closed 驗證。

    缺檔 → FileNotFoundError；非法 JSON / schema 不過 → ValueError。
    MUST NOT 回傳空或部分 manifest。
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"handoff manifest 不存在: {source}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"handoff manifest 解析失敗: {source}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"handoff manifest 格式錯誤（非 object）: {source}")

    result = contract.validate_handoff_message(payload, catalog)
    if not result.ok:
        raise ValueError(f"handoff manifest schema 不合法: {result.errors}")

    return payload
```

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase1_shadow_gate.py::HandoffManifestTests -q`
Expected: 4 passed。

---

### Task 3: render.py（① contract 注入）— TDD

**Files:**
- Test: `tests/test_persona_phase1_shadow_gate.py`（新增 `RenderContractPromptTests`）
- Create: `paulshaclaw/persona/render.py`

- [ ] **Step 1: 寫失敗測試（RED）**

在 `tests/test_persona_phase1_shadow_gate.py` 的 `HandoffManifestTests` 之後、`if __name__` 之前插入：

```python
class RenderContractPromptTests(unittest.TestCase):
    def test_contains_role_scope(self) -> None:
        from paulshaclaw.persona import render
        from paulshaclaw.persona.loader import load_catalog

        catalog = load_catalog()
        prompt = render.render_contract_prompt("builder", catalog=catalog)
        self.assertIsInstance(prompt, str)
        self.assertIn("builder", prompt)
        # 角色名與各 write_path 子字串皆須出現
        for write_path in catalog["builder"].write_paths:
            self.assertIn(write_path, prompt)
        # allowed_phases 與 effective_tools 也須體現（① 契約注入）
        self.assertIn("build", prompt)
        self.assertIn("git commit", prompt)

    def test_deterministic(self) -> None:
        from paulshaclaw.persona import render

        self.assertEqual(
            render.render_contract_prompt("reviewer"),
            render.render_contract_prompt("reviewer"),
        )

    def test_unknown_role_raises(self) -> None:
        from paulshaclaw.persona import render

        with self.assertRaises(ValueError):
            render.render_contract_prompt("nope")
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_persona_phase1_shadow_gate.py::RenderContractPromptTests -q`
Expected: RED，`ModuleNotFoundError: No module named 'paulshaclaw.persona.render'`。

- [ ] **Step 3: 實作 render.py（GREEN）**

建立 `paulshaclaw/persona/render.py`：

```python
from __future__ import annotations

from typing import Mapping

from . import context
from .contract import PersonaContract


def render_contract_prompt(
    role: str,
    catalog: Mapping[str, PersonaContract] | None = None,
    overlay: Mapping[str, object] | None = None,
) -> str:
    """把 persona 契約 render 成確定性的 prompt 前言（派工強制點 ①）。

    宣告 role / allowed_phases / write_paths / effective_tools。
    未知 role 由 build_persona_context 冒泡 ValueError。
    """
    ctx = context.build_persona_context(role=role, catalog=catalog, overlay=overlay)

    allowed_phases = ", ".join(ctx["allowed_phases"]) or "(none)"
    write_paths = "\n".join(f"  - {p}" for p in ctx["write_paths"])
    effective_tools = "\n".join(f"  - {t}" for t in ctx["effective_tools"])

    return (
        f"[PERSONA CONTRACT — role: {ctx['role']} (v{ctx['version']})]\n"
        "你在本次派工中扮演上述角色，且 MUST 嚴守以下契約邊界：\n"
        f"- allowed_phases: {allowed_phases}\n"
        "- write_paths（僅可寫入下列 glob，越界視為違規）:\n"
        f"{write_paths}\n"
        "- effective_tools（僅可使用下列工具）:\n"
        f"{effective_tools}\n"
        "[END PERSONA CONTRACT]"
    )
```

> 確定性說明：`build_persona_context` 的 `effective_tools` 已 `sorted`；`allowed_phases`／`write_paths` 維持契約宣告序。同輸入同輸出。

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase1_shadow_gate.py::RenderContractPromptTests -q`
Expected: 3 passed。

---

### Task 4: gate.py（② shadow diff-gate CLI）— TDD

**Files:**
- Test: `tests/test_persona_phase1_shadow_gate.py`（新增 `GateVerdictTests`、`GateExitCodeTests`）
- Create: `paulshaclaw/persona/gate.py`

- [ ] **Step 1: 寫失敗測試（RED）**

在 `tests/test_persona_phase1_shadow_gate.py` 插入下列兩組（沿用檔首 `_valid_manifest` helper）：

```python
def _write_manifest(tmp: Path) -> Path:
    from paulshaclaw.persona import handoff

    path = tmp / "runtime" / "handoff" / "persona-phase1-shadow-gate.json"
    handoff.write_manifest(path, _valid_manifest())
    return path


class GateVerdictTests(unittest.TestCase):
    def test_in_scope_ok(self) -> None:
        from paulshaclaw.persona import gate
        from paulshaclaw.persona.loader import load_catalog

        catalog = load_catalog()
        verdict = gate.build_verdict(
            role="builder",
            changed_paths=["paulshaclaw/persona/gate.py", "tests/test_x.py"],
            manifest_ok=True,
            catalog=catalog,
        )
        self.assertEqual(verdict["role"], "builder")
        self.assertEqual(verdict["changed_paths"], ["paulshaclaw/persona/gate.py", "tests/test_x.py"])
        self.assertEqual(verdict["violations"], [])
        self.assertTrue(verdict["handoff_ok"])
        self.assertTrue(verdict["ok"])

    def test_out_of_scope_violation(self) -> None:
        from paulshaclaw.persona import gate
        from paulshaclaw.persona.loader import load_catalog

        catalog = load_catalog()
        verdict = gate.build_verdict(
            role="builder",
            changed_paths=["paulshaclaw/persona/gate.py", "docs/secret.md"],
            manifest_ok=True,
            catalog=catalog,
        )
        self.assertFalse(verdict["ok"])
        offending = [v["path"] for v in verdict["violations"]]
        self.assertIn("docs/secret.md", offending)
        for v in verdict["violations"]:
            self.assertTrue(v["reason"])  # 帶可審計原因

    def test_manifest_not_ok_makes_verdict_fail(self) -> None:
        from paulshaclaw.persona import gate
        from paulshaclaw.persona.loader import load_catalog

        verdict = gate.build_verdict(
            role="builder",
            changed_paths=["paulshaclaw/persona/gate.py"],
            manifest_ok=False,
            catalog=load_catalog(),
        )
        self.assertFalse(verdict["handoff_ok"])
        self.assertFalse(verdict["ok"])

    def test_compute_changed_paths_real_git(self) -> None:
        from paulshaclaw.persona import gate

        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
            run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                            capture_output=True, env={**__import__("os").environ, **env})
            run("init", "-q", "-b", "main")
            (repo / "base.txt").write_text("x\n", encoding="utf-8")
            run("add", "-A")
            run("commit", "-q", "-m", "base")
            run("checkout", "-q", "-b", "feature/x")
            (repo / "paulshaclaw").mkdir()
            (repo / "paulshaclaw" / "new.py").write_text("y\n", encoding="utf-8")
            run("add", "-A")
            run("commit", "-q", "-m", "feat")
            paths = gate.compute_changed_paths("main", "feature/x", repo=repo)
            self.assertEqual(paths, ["paulshaclaw/new.py"])


class GateExitCodeTests(unittest.TestCase):
    def _patch_diff(self, gate_mod, paths: list[str]):
        original = gate_mod.compute_changed_paths
        gate_mod.compute_changed_paths = lambda base, head, repo=None: list(paths)
        self.addCleanup(setattr, gate_mod, "compute_changed_paths", original)

    def test_shadow_always_zero_enforce_one_on_violation(self) -> None:
        from paulshaclaw.persona import gate

        self._patch_diff(gate, ["docs/secret.md"])  # builder 越界
        with tempfile.TemporaryDirectory() as d:
            manifest = _write_manifest(Path(d))
            argv = ["--role", "builder", "--base", "main",
                    "--head", "feature/x", "--manifest", str(manifest)]
            self.assertEqual(gate.main(argv), 0)              # shadow 恆 0
            self.assertEqual(gate.main([*argv, "--enforce"]), 1)  # enforce 違規 → 1

    def test_in_scope_zero_in_both_modes(self) -> None:
        from paulshaclaw.persona import gate

        self._patch_diff(gate, ["paulshaclaw/persona/gate.py"])  # in-scope
        with tempfile.TemporaryDirectory() as d:
            manifest = _write_manifest(Path(d))
            argv = ["--role", "builder", "--base", "main",
                    "--head", "feature/x", "--manifest", str(manifest)]
            self.assertEqual(gate.main(argv), 0)
            self.assertEqual(gate.main([*argv, "--enforce"]), 0)
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_persona_phase1_shadow_gate.py::GateVerdictTests tests/test_persona_phase1_shadow_gate.py::GateExitCodeTests -q`
Expected: RED，`ModuleNotFoundError: No module named 'paulshaclaw.persona.gate'`。

- [ ] **Step 3: 實作 gate.py（GREEN）**

建立 `paulshaclaw/persona/gate.py`：

```python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from . import handoff
from .guardrail import PersonaGuardrail
from .loader import load_catalog


def compute_changed_paths(base: str, head: str, repo: str | Path | None = None) -> list[str]:
    """git diff --name-only base...head。非零 returncode → fail-closed（RuntimeError）。"""
    cmd = ["git"]
    if repo is not None:
        cmd += ["-C", str(repo)]
    cmd += ["diff", "--name-only", f"{base}...{head}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff 失敗（fail-closed）: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def evaluate_diff(
    role: str,
    changed_paths: Sequence[str],
    catalog: Mapping[str, object] | None = None,
) -> list[dict[str, str]]:
    """逐檔 evaluate_filesystem，回傳越界清單 [{path, reason}]。"""
    rail = PersonaGuardrail(catalog) if catalog is not None else PersonaGuardrail()
    violations: list[dict[str, str]] = []
    for path in changed_paths:
        decision = rail.evaluate_filesystem(role=role, path=path)
        if not decision.allowed:
            violations.append({"path": path, "reason": decision.reason})
    return violations


def load_manifest_ok(
    role: str,
    manifest_path: str | Path,
    catalog: Mapping[str, object] | None = None,
) -> bool:
    """讀驗 handoff manifest；任何 fail-closed 例外 → False（不放行）。"""
    try:
        handoff.read_manifest(manifest_path, catalog)
    except (FileNotFoundError, ValueError):
        return False
    return True


def build_verdict(
    *,
    role: str,
    changed_paths: Sequence[str],
    manifest_ok: bool,
    catalog: Mapping[str, object] | None = None,
) -> dict[str, object]:
    violations = evaluate_diff(role, changed_paths, catalog)
    ok = (not violations) and manifest_ok
    return {
        "role": role,
        "changed_paths": list(changed_paths),
        "violations": violations,
        "handoff_ok": manifest_ok,
        "ok": ok,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.persona.gate")
    parser.add_argument("--role", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo", default=None)
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="enforce 模式：ok 為 false 時 exit 1（預設 shadow 恆 exit 0）",
    )
    args = parser.parse_args(argv)

    catalog = load_catalog()
    try:
        changed_paths = compute_changed_paths(args.base, args.head, repo=args.repo)
        diff_error: str | None = None
    except RuntimeError as exc:  # fail-closed：無法取 diff 視為不可驗證
        changed_paths = []
        diff_error = str(exc)

    manifest_ok = load_manifest_ok(args.role, args.manifest, catalog)
    verdict = build_verdict(
        role=args.role,
        changed_paths=changed_paths,
        manifest_ok=manifest_ok,
        catalog=catalog,
    )
    verdict["mode"] = "enforce" if args.enforce else "shadow"
    if diff_error is not None:
        verdict["diff_error"] = diff_error
        verdict["ok"] = False

    print(json.dumps(verdict, ensure_ascii=False))

    if not args.enforce:
        return 0  # shadow：恆放行，僅觀測/記錄
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase1_shadow_gate.py::GateVerdictTests tests/test_persona_phase1_shadow_gate.py::GateExitCodeTests -q`
Expected: all passed。

---

### Task 5: 匯出 + 不回歸

**Files:**
- Modify: `paulshaclaw/persona/__init__.py`

- [ ] **Step 1: 匯出新模組**

把 `paulshaclaw/persona/__init__.py` 改為：

```python
"""Stage4 persona contract and guardrail primitives."""

from . import context, contract, gate, guardrail, handoff, render, shadow

__all__ = [
    "contract",
    "guardrail",
    "context",
    "shadow",
    "handoff",
    "render",
    "gate",
]
```

- [ ] **Step 2: 全套件不回歸**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠，**唯二允許失敗** 為 `tests/test_stage11_operator_cockpit.py` 的 textual/`query_one` 兩筆既知環境失敗；其餘任何失敗皆為真，須回到對應 Task 修。

- [ ] **Step 3: 既有 persona 測試針對性確認**

Run: `python -m pytest tests/test_stage4_persona_contract.py tests/test_persona_config_loader.py -q`
Expected: 全綠（Phase 1 不改既有判定邏輯，故行為不變）。

---

### Task 6: 驗證（設計 §11 Phase 1 獨立驗收）

- [ ] **Step 1: openspec 驗證**

Run: `openspec validate persona-phase1-shadow-gate --strict`
Expected: `Change 'persona-phase1-shadow-gate' is valid`。

- [ ] **Step 2: 對真分支跑 gate（shadow 恆放行）**

先寫一份 manifest：

```bash
python - <<'PY'
from paulshaclaw.persona import handoff
handoff.write_manifest(
    "runtime/handoff/persona-phase1-shadow-gate.json",
    {
        "from_role": "builder", "to_role": "reviewer", "phase": "review",
        "gate_status": "passed", "slice_id": "persona-phase1-shadow-gate",
        "summary": "phase1 shadow gate", "artifact_refs": ["feature/persona-phase1-shadow-gate"],
        "created_at": "2026-06-18T00:00:00+08:00",
        "base": "main", "head": "feature/persona-phase1-shadow-gate",
    },
)
print("manifest written")
PY
python -m paulshaclaw.persona.gate \
  --role builder --base main --head feature/persona-phase1-shadow-gate \
  --manifest runtime/handoff/persona-phase1-shadow-gate.json
echo "shadow exit=$?"
```

Expected: 印出 JSON verdict（`mode: shadow`），**exit 0**（即使本分支含 `openspec/**`／`docs/**` 等對 builder 越界的檔，shadow 仍恆放行——這正是 §11 Phase 1 的「恆放行」獨立驗收）。

> 註：`runtime/handoff/*.json` 屬執行期產物，勿納入本 change 的 production commit（僅供驗收手動產生）。

- [ ] **Step 3: enforce 旗標確認（可選）**

Run: 同上指令加 `--enforce`
Expected: 因本分支對 builder 越界，verdict `ok=false` → **exit 1**（驗證 enforce 退出碼路徑；非本階段預設）。

---

## Done When

- [ ] `handoff.py` / `render.py` / `gate.py` 三模組就位且 `__init__` 已匯出。
- [ ] `tests/test_persona_phase1_shadow_gate.py` 四組測試全綠。
- [ ] 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（除 2 個既知 stage11 textual 失敗）。
- [ ] `openspec validate persona-phase1-shadow-gate --strict` 通過。
- [ ] 對真分支跑 gate：shadow 恆 exit 0、verdict JSON 完整。
- [ ] 全程 local commit、**不 push/不開 PR/不 merge**（由 controller 在 gating 後處理）。
