# Persona Manager Phase A — 契約拼裝通電 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 persona 契約接上 coordinator 派工 —— 新增 `build_dispatch_command` 純函式（強制點 ①），讓 `dispatch_ready` 產出真 copilot 指令取代佔位註解，並把全域 `enforcement: shadow` 旗標顯式化。

**Architecture:** 三個小改動、零行為改變、零 live 接觸。`contract_command.build_dispatch_command` reuse 既有 `persona.render.render_contract_prompt`（純函式）把契約 render 成 prompt 前言、`shlex.join` 收成安全單行指令；`coordinator.autonomy.dispatch_ready` 改 import 之；`personas.yaml` 加頂層 `enforcement` key + `loader.load_enforcement` reader（目前無人消費，僅顯式化）。

**Tech Stack:** Python 3.12、stdlib（`shlex`、`pathlib`）、`PyYAML`、`unittest`（pytest 跑）。

**前置（動工一次）：** 本 repo branch policy（R-12）要求進 main 的 PR head 為 `feature/<slug>`。目前在 `main`，動工前先：
```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git pull --ff-only || git fetch --all --prune
git switch -c feature/persona-manager-phase-a
```
測試一律自 repo 根目錄跑：`python -m pytest <path> -v`。

---

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `paulshaclaw/persona/personas.yaml` | Modify | 加頂層 `enforcement: shadow`（§4 全域旗標） |
| `paulshaclaw/persona/loader.py` | Modify | 加 `load_enforcement()` reader（fail-safe 退 shadow） |
| `paulshaclaw/coordinator/contract_command.py` | Create | `build_dispatch_command` 純函式（強制點 ①） |
| `paulshaclaw/coordinator/autonomy.py` | Modify | `dispatch_ready` 改用 `build_dispatch_command` |
| `tests/test_persona_enforcement_flag.py` | Create | Task 1 測試 |
| `tests/test_coordinator_contract_command.py` | Create | Task 2 測試 |
| `tests/test_persona_phase4_fanout_autonomy.py` | Modify | Task 3 加一個契約指令斷言 |

---

## Task 1: `enforcement: shadow` 旗標 + `load_enforcement` reader

**Files:**
- Modify: `paulshaclaw/persona/personas.yaml`
- Modify: `paulshaclaw/persona/loader.py`
- Test: `tests/test_persona_enforcement_flag.py`

- [ ] **Step 1: 先加 yaml 旗標**（reader 測試才有預設值可驗）

`paulshaclaw/persona/personas.yaml` 第 1–2 行由：
```yaml
version: 1
roles:
```
改為：
```yaml
version: 1
enforcement: shadow
roles:
```
（`load_catalog` 只讀 `raw["roles"]`，新增頂層 key 不影響既有 catalog 載入。）

- [ ] **Step 2: 寫失敗測試**

Create `tests/test_persona_enforcement_flag.py`:
```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paulshaclaw.persona.loader import load_enforcement


class LoadEnforcementTests(unittest.TestCase):
    def test_default_yaml_is_shadow(self) -> None:
        self.assertEqual(load_enforcement(), "shadow")

    def test_explicit_enforce_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "personas.yaml"
            p.write_text("enforcement: enforce\nroles: {}\n", encoding="utf-8")
            self.assertEqual(load_enforcement(p), "enforce")

    def test_absent_key_defaults_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "personas.yaml"
            p.write_text("version: 1\nroles: {}\n", encoding="utf-8")
            self.assertEqual(load_enforcement(p), "shadow")

    def test_bogus_value_defaults_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "personas.yaml"
            p.write_text("enforcement: yolo\nroles: {}\n", encoding="utf-8")
            self.assertEqual(load_enforcement(p), "shadow")

    def test_missing_file_defaults_shadow(self) -> None:
        self.assertEqual(load_enforcement("/nonexistent/personas.yaml"), "shadow")

    def test_malformed_yaml_defaults_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "personas.yaml"
            p.write_text("enforcement: [unclosed\n", encoding="utf-8")
            self.assertEqual(load_enforcement(p), "shadow")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/test_persona_enforcement_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_enforcement'`

- [ ] **Step 4: 實作 `load_enforcement`**

`paulshaclaw/persona/loader.py` 在 `DEFAULT_PERSONAS_PATH = ...` 那行之後加：
```python
_VALID_ENFORCEMENT = ("shadow", "enforce")
DEFAULT_ENFORCEMENT = "shadow"


def load_enforcement(path: str | Path | None = None) -> str:
    """讀 personas.yaml 頂層 `enforcement`（全域護欄模式）。

    fail-safe：缺檔／壞 YAML／缺 key／非法值一律退 'shadow'（最保守，
    永不誤翻 enforce）。僅認字面 'shadow' / 'enforce'。
    """
    source = Path(path) if path is not None else DEFAULT_PERSONAS_PATH
    if not source.is_file():
        return DEFAULT_ENFORCEMENT
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return DEFAULT_ENFORCEMENT
    if not isinstance(raw, Mapping):
        return DEFAULT_ENFORCEMENT
    value = raw.get("enforcement")
    return value if value in _VALID_ENFORCEMENT else DEFAULT_ENFORCEMENT
```
（`Path`、`Mapping`、`yaml` 皆已在 `loader.py` 頂部 import，無須新增。）

- [ ] **Step 5: 跑測試確認通過**

Run: `python -m pytest tests/test_persona_enforcement_flag.py -v`
Expected: PASS（6 passed）

- [ ] **Step 6: 確認既有 persona 測試不回歸**

Run: `python -m pytest tests/test_persona_config_loader.py -v`
Expected: PASS（既有測試全綠）

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/persona/personas.yaml paulshaclaw/persona/loader.py tests/test_persona_enforcement_flag.py
git commit -m "$(cat <<'EOF'
feat(persona): personas.yaml 補全域 enforcement 旗標 + load_enforcement reader

§4 全域 shadow/enforce 旗標顯式化；fail-safe 退 shadow，目前無人消費（零行為改變）。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `build_dispatch_command` 純函式（強制點 ①）

**Files:**
- Create: `paulshaclaw/coordinator/contract_command.py`
- Test: `tests/test_coordinator_contract_command.py`

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_coordinator_contract_command.py`:
```python
from __future__ import annotations

import shlex
import unittest

from paulshaclaw.coordinator.contract_command import (
    DEFAULT_EXECUTOR,
    build_dispatch_command,
)


class BuildDispatchCommandTests(unittest.TestCase):
    def test_carries_contract_task_and_plan(self) -> None:
        cmd = build_dispatch_command(
            "builder", task="persona-phase-a", plan_path="docs/superpowers/plans/p.md"
        )
        self.assertIn("[PERSONA CONTRACT", cmd)
        self.assertIn("role: builder", cmd)
        self.assertIn("persona-phase-a", cmd)
        self.assertIn("docs/superpowers/plans/p.md", cmd)
        self.assertIn("copilot", cmd)

    def test_prompt_is_single_shlex_token(self) -> None:
        cmd = build_dispatch_command("builder", task="t", plan_path="p.md")
        parts = shlex.split(cmd)
        # executor 前綴原樣 + 剛好一個 prompt 參數
        self.assertEqual(parts[: len(DEFAULT_EXECUTOR)], list(DEFAULT_EXECUTOR))
        self.assertEqual(len(parts), len(DEFAULT_EXECUTOR) + 1)

    def test_unknown_role_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_dispatch_command("nobody", task="t", plan_path="p.md")

    def test_is_pure_no_file_read(self) -> None:
        # plan_path 不存在也不該 raise（純字串函式、零 I/O）
        cmd = build_dispatch_command("builder", task="t", plan_path="/nope/x.md")
        self.assertIn("/nope/x.md", cmd)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_coordinator_contract_command.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paulshaclaw.coordinator.contract_command'`

- [ ] **Step 3: 實作**

Create `paulshaclaw/coordinator/contract_command.py`:
```python
from __future__ import annotations

import shlex
from typing import Mapping

from paulshaclaw.persona import render
from paulshaclaw.persona.contract import PersonaContract

# 預設 executor 前綴：builder 首發 copilot one-shot（設計 §3）。
DEFAULT_EXECUTOR: tuple[str, ...] = ("copilot", "--model", "gpt-5.4", "--yolo", "-p")


def build_dispatch_command(
    role: str,
    *,
    task: str,
    plan_path: str,
    executor: tuple[str, ...] = DEFAULT_EXECUTOR,
    catalog: Mapping[str, PersonaContract] | None = None,
) -> str:
    """強制點 ①：把 persona 契約 render 成 prompt 前言，拼成可送進 pane 的單行指令。

    純字串函式、零 I/O：只嵌 plan_path 參照（copilot 於 worktree 內自行讀計畫），
    不在此讀檔。未知 role → ValueError（由 render_contract_prompt 冒泡）。
    以 shlex.join 收尾，prompt 為單一安全 token（TmuxPaneSender 以 -l literal 送）。
    """
    contract_prompt = render.render_contract_prompt(role, catalog)
    prompt = (
        f"{contract_prompt}\n\n"
        f"[TASK] {task}\n"
        f"[PLAN: {plan_path}]\n"
        "請於本 worktree 內讀取上述 plan 並依 persona 契約邊界執行。"
    )
    return shlex.join([*executor, prompt])
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_coordinator_contract_command.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/coordinator/contract_command.py tests/test_coordinator_contract_command.py
git commit -m "$(cat <<'EOF'
feat(coordinator): build_dispatch_command 把 persona 契約 render 進派工指令（強制點 ①）

coordinator→persona 的那條線（Gap A）。純字串函式、零 I/O；reuse render_contract_prompt。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `dispatch_ready` 改用 `build_dispatch_command`（取代佔位）

**Files:**
- Modify: `paulshaclaw/coordinator/autonomy.py`
- Test: `tests/test_persona_phase4_fanout_autonomy.py`

- [ ] **Step 1: 寫失敗測試**（加進既有 phase4 測試檔的 `DispatchReadyTests` 類別內，緊接 `test_dispatch_ready_dispatches_exactly_ready_set` 之後）

在 `tests/test_persona_phase4_fanout_autonomy.py` 加入：
```python
    def test_dispatch_ready_command_carries_persona_contract(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready

        fake = _FakeDispatcher()
        metas = [_meta("slice-a", plan="docs/superpowers/plans/a.md")]
        dispatch_ready(metas, is_satisfied=lambda _id: True, dispatcher=fake, persona="builder")

        self.assertEqual(len(fake.calls), 1)
        command = fake.calls[0]["command"]
        self.assertIn("[PERSONA CONTRACT", command)        # 不再是 "# dispatch ..." 佔位
        self.assertIn("role: builder", command)
        self.assertIn("docs/superpowers/plans/a.md", command)
        self.assertIn("copilot", command)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest "tests/test_persona_phase4_fanout_autonomy.py::DispatchReadyTests::test_dispatch_ready_command_carries_persona_contract" -v`
Expected: FAIL — `AssertionError: '[PERSONA CONTRACT' not found in '# dispatch slice-a (plan=docs/superpowers/plans/a.md)'`

- [ ] **Step 3: 實作 — 接上 build_dispatch_command**

在 `paulshaclaw/coordinator/autonomy.py` 頂部 import 區（`import yaml` 之後）加：
```python
from .contract_command import build_dispatch_command
```

`dispatch_ready` 內，把：
```python
        kwargs = {
            "task": slice_id,
            "persona": persona,
            "pane_id": f"%{i}",
            "command": f"# dispatch {slice_id} (plan={m['plan']})",
        }
```
改為：
```python
        kwargs = {
            "task": slice_id,
            "persona": persona,
            "pane_id": f"%{i}",
            "command": build_dispatch_command(persona, task=slice_id, plan_path=m["plan"]),
        }
```

- [ ] **Step 4: 跑新測試確認通過**

Run: `python -m pytest "tests/test_persona_phase4_fanout_autonomy.py::DispatchReadyTests::test_dispatch_ready_command_carries_persona_contract" -v`
Expected: PASS

- [ ] **Step 5: 跑整個 phase4 檔確認不回歸**

Run: `python -m pytest tests/test_persona_phase4_fanout_autonomy.py -v`
Expected: PASS（既有測試僅斷言 `task`/`persona`，不碰 `command` 內容，故全綠）

- [ ] **Step 6: 全測試套件回歸閘門**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: PASS（與 CI 同綠；無回歸）

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/coordinator/autonomy.py tests/test_persona_phase4_fanout_autonomy.py
git commit -m "$(cat <<'EOF'
feat(coordinator): dispatch_ready 改用 build_dispatch_command 產真派工指令

接上 Gap A —— fan-out 不再送佔位註解，改送 render 過契約的 copilot 指令。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## 完成定義（Phase A 驗收）

- [ ] `personas.yaml` 有 `enforcement: shadow`；`load_enforcement()` 可讀、fail-safe 退 shadow。
- [ ] `build_dispatch_command` 對三角色 render 出含契約段的 copilot 指令；未知 role raise。
- [ ] `dispatch_ready` 派出的 command 是真契約指令（非佔位）。
- [ ] `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 全綠（零行為回歸）。
- [ ] 零 live 接觸（未碰 daemon / systemd / tmux / 真 copilot）。

## Self-Review 紀錄

- **Spec 覆蓋**：對應 spec §7 Phase A 三項（`build_dispatch_command` ✓ Task 2、`dispatch_ready` 改用 ✓ Task 3、`personas.yaml` 補 enforcement ✓ Task 1）。Phase B（PaneAllocator）/ C（systemd）/ D（canary）不在本計畫，符合「第一個計畫鎖 Phase A」。
- **Placeholder 掃描**：無 TBD/TODO；每個 code step 皆含完整程式碼與確切指令、預期輸出。
- **型別一致**：`build_dispatch_command(role, *, task, plan_path, executor, catalog)` 簽章在 Task 2 定義、Task 3 以 `build_dispatch_command(persona, task=slice_id, plan_path=m["plan"])` 呼叫一致；`DEFAULT_EXECUTOR` 為 `tuple[str, ...]`，測試與實作一致；`load_enforcement(path=None)` 簽章 Task 1 定義與測試一致。
