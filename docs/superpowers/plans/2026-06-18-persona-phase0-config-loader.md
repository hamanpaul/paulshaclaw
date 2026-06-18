# Persona Phase 0 — Catalog Config 化 + Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 persona catalog 從寫死於 `contract.py` 改為 `personas.yaml` + fail-closed loader，並依多 agent 派工流程重定義三角色 scope（v2），不改 guardrail/context/shadow 的公開 API。

**Architecture:** 新增 `personas.yaml`（package-local 預設）與 `loader.py`（`load_catalog(path=None)`，reuse `validate_persona_schema`、缺檔/非法 raise）。`contract.py` 於模組底部由 loader 載入 `PERSONA_CATALOG`（bottom-import 避免循環相依），對 consumer 維持原匯出介面。因 persona 目前無 runtime 消費者，catalog 值變更僅影響單元測試。

**Tech Stack:** Python 3.12、`unittest`、PyYAML（已是相依，`requirements-stage9.txt`）。

---

## File Structure

- Create: `paulshaclaw/persona/personas.yaml` — 三角色 v2 契約宣告（catalog 唯一事實來源）
- Create: `paulshaclaw/persona/loader.py` — `load_catalog()`，fail-closed
- Modify: `paulshaclaw/persona/contract.py:31-81` — 移除寫死 `PERSONA_CATALOG` literal，改為底部 `load_catalog()`
- Create: `tests/test_persona_config_loader.py` — loader + v2 scope RED 測試
- Commit-only: `docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md`、`openspec/changes/persona-phase0-config-loader/**`、本 plan

---

### Task 1: 提交規劃 artifacts

**Files:**
- Commit: design spec、openspec change（proposal/design/specs/tasks）、本 plan

- [ ] **Step 1: 確認分支與待提交檔**

Run: `git branch --show-current && git status --short`
Expected: 分支 `feature/persona-dispatch-guardrail`；列出未追蹤的 design spec、`openspec/changes/persona-phase0-config-loader/`、plan。

- [ ] **Step 2: 提交規劃 artifacts**

```bash
git add docs/superpowers/specs/2026-06-18-persona-dispatch-guardrail-design.md \
        docs/superpowers/plans/2026-06-18-persona-phase0-config-loader.md \
        openspec/changes/persona-phase0-config-loader
git commit -m "$(cat <<'EOF'
docs(persona): persona 派工護欄設計 + Phase 0 openspec change

設計 5 階段整合（①②③ 護欄、coordinator CLI、自建 CI 硬後盾、fan-out）；
Phase 0 鎖 catalog config 化 + loader。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: personas.yaml + loader（TDD）

**Files:**
- Test: `tests/test_persona_config_loader.py`
- Create: `paulshaclaw/persona/personas.yaml`
- Create: `paulshaclaw/persona/loader.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_persona_config_loader.py`：

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paulshaclaw.persona import contract, guardrail
from paulshaclaw.persona.loader import load_catalog


class LoadCatalogTests(unittest.TestCase):
    def test_default_catalog_loads_three_roles(self) -> None:
        catalog = load_catalog()
        self.assertEqual(set(catalog), {"manager", "builder", "reviewer"})
        self.assertTrue(contract.validate_persona_schema(catalog).ok)

    def test_missing_file_fails_closed(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_catalog("/nonexistent/personas.yaml")

    def test_invalid_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "personas.yaml"
            bad.write_text("roles:\n  manager:\n    role: manager\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog(bad)


class RoleV2ScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rail = guardrail.PersonaGuardrail(load_catalog())

    def test_manager_can_write_openspec(self) -> None:
        self.assertTrue(
            self.rail.evaluate_filesystem(role="manager", path="openspec/changes/x/proposal.md").allowed
        )

    def test_builder_archive_yes_push_no_commit_yes(self) -> None:
        self.assertTrue(
            self.rail.evaluate_filesystem(role="builder", path="openspec/changes/archive/x/spec.md").allowed
        )
        self.assertFalse(self.rail.evaluate_tool(role="builder", tool="git push").allowed)
        self.assertTrue(self.rail.evaluate_tool(role="builder", tool="git commit").allowed)

    def test_reviewer_only_reports(self) -> None:
        self.assertTrue(
            self.rail.evaluate_filesystem(role="reviewer", path="reports/review/r.md").allowed
        )
        self.assertFalse(
            self.rail.evaluate_filesystem(role="reviewer", path="paulshaclaw/x.py").allowed
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED（預期原因）**

Run: `python -m pytest tests/test_persona_config_loader.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'paulshaclaw.persona.loader'`（loader/yaml 尚不存在）。截圖/存輸出為證據。

- [ ] **Step 3: 建立 `paulshaclaw/persona/personas.yaml`**

```yaml
version: 1
roles:
  manager:
    role: manager
    version: "2.0.0"
    summary: orchestrates lifecycle, dispatch, policy/commit/push/PR, merge, fix dispatch, task triage
    allowed_phases: [research, define, plan, build, verify, review, ship]
    write_paths: ["docs/**", "openspec/**", "lifecycle.yaml", "runtime/handoff/**"]
    allowed_tools: ["coordinator.dispatch", "coordinator.handoff", "git", "gh", "openspec", "python -m unittest"]
  builder:
    role: builder
    version: "2.0.0"
    summary: implements approved build slices within bounded scope (copilot first, fixers after)
    allowed_phases: [build]
    write_paths: ["paulshaclaw/**", "tests/**", "openspec/changes/archive/**"]
    allowed_tools: ["python -m unittest", "rg", "edit", "git add", "git commit"]
  reviewer:
    role: reviewer
    version: "2.0.0"
    summary: reviews artifacts and records verdicts without code edits
    allowed_phases: [review]
    write_paths: ["reports/review/**"]
    allowed_tools: ["python -m unittest", "rg"]
```

- [ ] **Step 4: 建立 `paulshaclaw/persona/loader.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

from .contract import PersonaContract, validate_persona_schema

DEFAULT_PERSONAS_PATH = Path(__file__).with_name("personas.yaml")


def load_catalog(path: str | Path | None = None) -> dict[str, PersonaContract]:
    source = Path(path) if path is not None else DEFAULT_PERSONAS_PATH
    if not source.is_file():
        raise FileNotFoundError(f"persona catalog 不存在: {source}")
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"persona catalog 解析失敗: {source}: {exc}") from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("roles"), Mapping):
        raise ValueError(f"persona catalog 格式錯誤（缺 roles）: {source}")

    records = raw["roles"]
    result = validate_persona_schema(records)
    if not result.ok:
        raise ValueError(f"persona catalog schema 不合法: {result.errors}")

    catalog: dict[str, PersonaContract] = {}
    for role, rec in records.items():
        catalog[role] = PersonaContract(
            role=rec["role"],
            version=rec["version"],
            summary=rec["summary"],
            allowed_phases=tuple(rec["allowed_phases"]),
            write_paths=tuple(rec["write_paths"]),
            allowed_tools=tuple(rec["allowed_tools"]),
        )
    return catalog
```

- [ ] **Step 5: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_persona_config_loader.py -q`
Expected: PASS（6 tests）。

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/persona/personas.yaml paulshaclaw/persona/loader.py tests/test_persona_config_loader.py
git commit -m "$(cat <<'EOF'
feat(persona): personas.yaml + fail-closed loader（Phase 0）

catalog 改 config-driven；三角色 v2 scope（manager+openspec/handoff、
builder+archive/本地git、reviewer reports-only）。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 接線 contract.PERSONA_CATALOG 由 loader 載入（TDD）

**Files:**
- Modify: `paulshaclaw/persona/contract.py:31-81`（移除寫死 literal）
- Test: `tests/test_persona_config_loader.py`（加一個來源一致性測試）

- [ ] **Step 1: 加失敗測試（來源一致性）**

在 `tests/test_persona_config_loader.py` 的 `LoadCatalogTests` 內新增：

```python
    def test_contract_catalog_sourced_from_yaml(self) -> None:
        # PERSONA_CATALOG 應等同 loader 載入結果（builder 含 archive scope）
        self.assertEqual(
            set(contract.PERSONA_CATALOG["builder"].write_paths),
            {"paulshaclaw/**", "tests/**", "openspec/changes/archive/**"},
        )
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_persona_config_loader.py::LoadCatalogTests::test_contract_catalog_sourced_from_yaml -q`
Expected: FAIL（現 `contract.PERSONA_CATALOG` 是舊寫死值，builder write_paths 無 `openspec/changes/archive/**`）。

- [ ] **Step 3: 改 contract.py — 移除寫死 literal，底部由 loader 載入**

刪除 `contract.py` 第 31-81 行的 `PERSONA_CATALOG: dict[str, PersonaContract] = { ... }` 整段 literal。於檔案**最底部**（所有定義之後）新增：

```python
from .loader import load_catalog  # noqa: E402  bottom-import 避免與 loader 循環相依

PERSONA_CATALOG: dict[str, PersonaContract] = load_catalog()
```

> 說明：`loader.py` 於模組頂 `from .contract import PersonaContract, validate_persona_schema`；該二者在 contract 底部 import 之前已定義，故循環安全。`PERSONA_CATALOG` 僅在各函式呼叫時被參照（`catalog or PERSONA_CATALOG`），不影響 import。

- [ ] **Step 4: 跑 persona 全測試確認 GREEN（含既有）**

Run: `python -m pytest tests/test_persona_config_loader.py tests/test_stage4_persona_contract.py -q`
Expected: PASS（含既有 PersonaSchema/RoleBaseline/AllowedPhases/Handoff/Guardrail/ShadowRun 全綠）。

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/persona/contract.py tests/test_persona_config_loader.py
git commit -m "$(cat <<'EOF'
refactor(persona): PERSONA_CATALOG 改由 loader 載入，移除寫死 literal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 全套件回歸 + openspec 驗證（verify）

- [ ] **Step 1: 全套件回歸（沿用 CI 指令）**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠（除既有與本變更無關的 cockpit textual env 假象外；CI 環境含 textual 全綠）。確認無新增 fail。

- [ ] **Step 2: openspec 驗證**

Run: `openspec validate persona-phase0-config-loader --strict && openspec status --change persona-phase0-config-loader`
Expected: valid、4/4 artifacts complete。

- [ ] **Step 3: 標記 tasks.md 完成項**

將 `openspec/changes/persona-phase0-config-loader/tasks.md` 對應 checkbox 打勾並 commit（`docs(persona): tasks.md 勾選 Phase 0 完成項`）。

---

## Self-Review

- **Spec coverage**：delta spec 兩條 requirement（config-driven 三角色基線 MODIFIED、fail-closed loader ADDED）皆對映 Task 2/3 與測試。✓
- **Placeholder scan**：無 TBD/TODO；每段 code step 皆含完整 code。✓
- **Type consistency**：`load_catalog` 簽名、`PersonaContract` 欄位（role/version/summary/allowed_phases/write_paths/allowed_tools）、`guardrail.PersonaGuardrail(catalog)` 用法跨 Task 一致。✓
- **循環相依**：Task 3 已說明 bottom-import 安全性。✓
