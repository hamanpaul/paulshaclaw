# Persona Phase 4 — Manager Fan-out + Autonomy Gate + depends_on DAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付設計 §9（manager fan-out + autonomy gate）與 issue [#104](https://github.com/hamanpaul/paulshaclaw/issues/104)（depends_on DAG）。新增 `paulshaclaw/coordinator/autonomy.py`（frontmatter 解析、spec 掃描、循環相依偵測、就緒判定、fan-out）＋擴充 `paulshaclaw/coordinator/cli.py`（`ready` / `fanout` 子命令）。fan-out **reuse Phase 2 `Dispatcher`**，不重寫 dispatch/registry 邏輯。

**Architecture:** 鐵律延續 Phase 2——**所有副作用藏在可注入 seam 後，單元測試一律注入 fake**：不啟動真 copilot、真 tmux、真 git。

- `autonomy.parse_spec_frontmatter(path)`：`yaml.safe_load` 解析開頭 `---` block，回 `{path, dispatch, slice_id, plan, depends_on}`。**預設 HOLD**：無合法 frontmatter / 無 `dispatch` key / 值非 `auto` 一律 `dispatch='hold'`。
- `autonomy.scan_specs(specs_dir)`：`sorted(glob('*.md'))` 逐檔解析，回 metas（確定性序）；目錄不存在 → `[]`。
- `autonomy.detect_cycles(metas)`：`slice_id` 為節點、`depends_on` 為邊，DFS 三色偵測回邊 → `raise ValueError`；指向不存在 id 的邊不算環。
- `autonomy.ready_units(metas, is_satisfied)`：**先 `detect_cycles`**；回 `dispatch=='auto'` ∧ `plan` 非空 ∧ `all(is_satisfied(dep) ...)`；`is_satisfied` **必注入**（#104 把判定來源留開放）。
- `autonomy.default_is_satisfied(slice_id, handoff_dir)`：預設來源 = handoff `gate_status=='passed'`（fail-closed），但保持可注入覆寫。
- `autonomy.dispatch_ready(metas, is_satisfied, dispatcher, persona='builder')`：算就緒集，對每單位 `dispatcher.dispatch(...)` 各派一筆（reuse Phase 2 `Dispatcher`，duck-typed），回 jobs。
- `cli.main(argv, *, registry=None, pane_sender=None, worktree_creator=None, is_satisfied=None)`：在 Phase 2 簽名上加 `is_satisfied`；`ready` / `fanout` 子命令；循環相依 → stderr + exit 非零。

**Tech Stack:** Python 3.12、`unittest`、PyYAML（既有依賴）、stdlib（`json`、`argparse`、`pathlib`、`tempfile`、`functools`、`typing`）。無新增外部依賴。

**Hard constraints（務必遵守）:**
- **不改** `paulshaclaw/core/daemon.py`、`paulshaclaw/core/config.py`（scope 紀律）。
- **不重寫** `paulshaclaw/coordinator/{dispatcher,registry,seams}.py`——reuse Phase 2；`dispatch_ready` 僅 orchestrate（呼 `Dispatcher.dispatch`）。
- 預設 **HOLD**：沒 `dispatch: auto` 的 spec 永不自主派工。
- `depends_on` 成環 → **raise / refuse**（不派任何工）。
- 相依「滿足」判定來源 **pluggable**：注入 `is_satisfied(slice_id) -> bool`；提供 `default_is_satisfied` 一個預設，但保持可注入。
- 測試**不得**啟動真 copilot / 真 tmux / 真 git——一律注入 fake（fake dispatcher 或真 `Dispatcher` + fake seam）。

**Out of scope（後續/他線）:** persona ①②③ contract render／gate（Phase 1/3）；把 daemon 接到真 coordinator（wiring）；真實 pane 分配與 copilot prompt 拼裝（§5 ①）；`is_satisfied` 終局來源定案（merged-to-main vs gate_status，#104 留開放，本 change 用 pluggable predicate 吸收）。

---

## File Structure

- Commit-only（本 docs commit）：`openspec/changes/persona-phase4-fanout-autonomy/**`、本 plan
- Create: `tests/test_persona_phase4_fanout_autonomy.py` — 六組 RED 測試（Frontmatter/Scan/Cycle/Ready/Fanout/Cli）
- Create: `paulshaclaw/coordinator/autonomy.py` — frontmatter 解析 + scan + DAG + ready + fan-out + default_is_satisfied
- Modify: `paulshaclaw/coordinator/cli.py` — 新增 `ready` / `fanout` 子命令、`main(argv)` 加 `is_satisfied`
- Modify: `paulshaclaw/coordinator/__init__.py` — 匯出 `autonomy`（不動其餘）

**全套件測試指令（CI 同款）：** `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
**唯一可接受的既知失敗：** `tests/test_stage11_operator_cockpit.py` 2 筆（`query_one` / textual 未裝於 system python3）。另 `test_hooks.py` / `test_importer_cli.py` / `test_skillopt_loop.py` 在全套件資源壓力下偶發 flake（既有 test-isolation 問題，非本 change）——若其一失敗，單獨重跑確認綠，回報為 known flake，**不**當本 change 回歸。

---

## 設計關鍵不變式（實作前先讀）

1. **預設 HOLD（硬約束）**：`parse_spec_frontmatter` 只在 frontmatter 字面值為 `auto` 時回 `dispatch='auto'`，其餘全 `'hold'`。fail-safe 方向：誤判只會「不派」，不會「亂派」。
2. **循環相依 refuse**：`ready_units` MUST 先 `detect_cycles`；成環整批 raise，不回部分就緒集。
3. **三條件就緒**：`dispatch=='auto'` ∧ `plan` 非空字串 ∧ `all(is_satisfied(dep) for dep in depends_on)`。`depends_on` 空 → `all([])==True` 自然滿足。
4. **is_satisfied 必注入**：`ready_units` / `dispatch_ready` 的 `is_satisfied` 無預設參數值（強制呼叫者決定來源）。`default_is_satisfied` 只是 CLI 未注入時的後援。
5. **reuse Phase 2 Dispatcher**：`dispatch_ready` 不 import 也不重寫 registry/seams 邏輯；只呼注入物的 `dispatch(task, persona, pane_id, command)`（與 Phase 2 簽名一致）。
6. **不算環的外部相依**：`depends_on` 指向不在 metas 的 `slice_id` 不算環（交給 `is_satisfied`）；只有回路才 raise。

---

## Task 1 — 提交 openspec change + 本 plan（docs commit）

- [ ] 1.1 確認 `openspec/changes/persona-phase4-fanout-autonomy/{proposal,design,tasks}.md` 與 `specs/coordinator-cli/spec.md` 已就位
- [ ] 1.2 `openspec validate persona-phase4-fanout-autonomy --strict` 通過
- [ ] 1.3 提交本 docs commit（見文末「Commits」）。**僅 docs**；不含任何 production code

---

## Task 2 — TDD RED：新增 `tests/test_persona_phase4_fanout_autonomy.py`

先寫全部六組失敗測試（模組尚不存在 → RED）。以下為**完整測試檔內容**（無 placeholder）：

```python
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path


# --------------------------------------------------------------------------- #
# helpers：寫 spec fixture / handoff fixture
# --------------------------------------------------------------------------- #
def _write_spec(dirpath: Path, name: str, frontmatter: str | None, body: str = "x") -> Path:
    """寫一份 spec markdown。frontmatter=None → 無 frontmatter（不以 --- 起頭）。"""
    p = dirpath / name
    if frontmatter is None:
        p.write_text(body + "\n", encoding="utf-8")
    else:
        p.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return p


def _meta(slice_id, *, dispatch="auto", plan="docs/plan.md", depends_on=None, path=None):
    return {
        "path": path or f"/specs/{slice_id}.md",
        "dispatch": dispatch,
        "slice_id": slice_id,
        "plan": plan,
        "depends_on": list(depends_on or []),
    }


class _FakeDispatcher:
    """記錄 dispatch 呼叫的 fake；duck-typed 相容 Phase 2 Dispatcher.dispatch。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def dispatch(self, *, task, persona, pane_id, command):
        job = {
            "job_id": f"{task}-{len(self.calls) + 1}",
            "task": task,
            "persona": persona,
            "pane": pane_id,
            "command": command,
            "status": "dispatched",
        }
        self.calls.append(job)
        return job


# --------------------------------------------------------------------------- #
# FrontmatterTests
# --------------------------------------------------------------------------- #
class FrontmatterTests(unittest.TestCase):
    def test_parse_auto_with_depends_on(self) -> None:
        from paulshaclaw.coordinator.autonomy import parse_spec_frontmatter

        with tempfile.TemporaryDirectory() as d:
            p = _write_spec(
                Path(d), "a.md",
                "dispatch: auto\n"
                "slice_id: persona-phase1-shadow-gate\n"
                "plan: docs/superpowers/plans/p1.md\n"
                "depends_on: [persona-phase0-config-loader, other]",
            )
            meta = parse_spec_frontmatter(p)
            self.assertEqual(meta["dispatch"], "auto")
            self.assertEqual(meta["slice_id"], "persona-phase1-shadow-gate")
            self.assertEqual(meta["plan"], "docs/superpowers/plans/p1.md")
            self.assertEqual(meta["depends_on"], ["persona-phase0-config-loader", "other"])
            self.assertEqual(meta["path"], str(p))

    def test_parse_hold_and_default(self) -> None:
        from paulshaclaw.coordinator.autonomy import parse_spec_frontmatter

        with tempfile.TemporaryDirectory() as d:
            hold = parse_spec_frontmatter(
                _write_spec(Path(d), "hold.md", "dispatch: hold\nslice_id: s1")
            )
            self.assertEqual(hold["dispatch"], "hold")
            self.assertEqual(hold["depends_on"], [])

            typo = parse_spec_frontmatter(
                _write_spec(Path(d), "typo.md", "dispatch: AUTO_TYPO\nslice_id: s2")
            )
            self.assertEqual(typo["dispatch"], "hold")  # 非字面 auto → hold

            nokey = parse_spec_frontmatter(
                _write_spec(Path(d), "nokey.md", "slice_id: s3\nplan: docs/p.md")
            )
            self.assertEqual(nokey["dispatch"], "hold")  # 缺 dispatch key → hold
            self.assertEqual(nokey["slice_id"], "s3")

    def test_parse_missing_frontmatter_is_hold(self) -> None:
        from paulshaclaw.coordinator.autonomy import parse_spec_frontmatter

        with tempfile.TemporaryDirectory() as d:
            meta = parse_spec_frontmatter(
                _write_spec(Path(d), "plain.md", None, body="# 純內文，無 frontmatter")
            )
            self.assertEqual(meta["dispatch"], "hold")
            self.assertIsNone(meta["slice_id"])
            self.assertIsNone(meta["plan"])
            self.assertEqual(meta["depends_on"], [])

    def test_parse_depends_on_scalar_coerced(self) -> None:
        from paulshaclaw.coordinator.autonomy import parse_spec_frontmatter

        with tempfile.TemporaryDirectory() as d:
            meta = parse_spec_frontmatter(
                _write_spec(Path(d), "scalar.md", "dispatch: auto\nslice_id: s\ndepends_on: only-one")
            )
            self.assertEqual(meta["depends_on"], ["only-one"])  # 單一字串容錯成 list


# --------------------------------------------------------------------------- #
# ScanTests
# --------------------------------------------------------------------------- #
class ScanTests(unittest.TestCase):
    def test_scan_specs_deterministic(self) -> None:
        from paulshaclaw.coordinator.autonomy import scan_specs

        with tempfile.TemporaryDirectory() as d:
            _write_spec(Path(d), "b.md", "dispatch: auto\nslice_id: b\nplan: p")
            _write_spec(Path(d), "a.md", "dispatch: hold\nslice_id: a")
            _write_spec(Path(d), "c.md", None)  # 無 frontmatter
            metas = scan_specs(d)
            self.assertEqual(len(metas), 3)
            # 確定性：依 path 排序 → a, b, c
            slugs = [Path(m["path"]).name for m in metas]
            self.assertEqual(slugs, ["a.md", "b.md", "c.md"])

    def test_scan_missing_dir_returns_empty(self) -> None:
        from paulshaclaw.coordinator.autonomy import scan_specs

        self.assertEqual(scan_specs("/no/such/dir/xyz"), [])


# --------------------------------------------------------------------------- #
# CycleTests
# --------------------------------------------------------------------------- #
class CycleTests(unittest.TestCase):
    def test_detect_cycle_raises(self) -> None:
        from paulshaclaw.coordinator.autonomy import detect_cycles

        direct = [_meta("A", depends_on=["B"]), _meta("B", depends_on=["A"])]
        with self.assertRaises(ValueError):
            detect_cycles(direct)

        indirect = [
            _meta("A", depends_on=["B"]),
            _meta("B", depends_on=["C"]),
            _meta("C", depends_on=["A"]),
        ]
        with self.assertRaises(ValueError):
            detect_cycles(indirect)

        # 非環圖：A→B、C→B（DAG）→ 不 raise
        acyclic = [
            _meta("A", depends_on=["B"]),
            _meta("B", depends_on=[]),
            _meta("C", depends_on=["B"]),
        ]
        detect_cycles(acyclic)  # MUST NOT raise

    def test_external_dep_not_a_cycle(self) -> None:
        from paulshaclaw.coordinator.autonomy import detect_cycles

        # depends_on 指向不在 metas 的 id（外部/未掃到）→ 不算環
        detect_cycles([_meta("A", depends_on=["not-scanned"])])  # MUST NOT raise

    def test_ready_units_refuses_on_cycle(self) -> None:
        from paulshaclaw.coordinator.autonomy import ready_units

        metas = [_meta("A", depends_on=["B"]), _meta("B", depends_on=["A"])]
        with self.assertRaises(ValueError):
            ready_units(metas, is_satisfied=lambda _id: True)


# --------------------------------------------------------------------------- #
# ReadyTests
# --------------------------------------------------------------------------- #
class ReadyTests(unittest.TestCase):
    def test_hold_not_ready(self) -> None:
        from paulshaclaw.coordinator.autonomy import ready_units

        metas = [
            _meta("held", dispatch="hold"),          # hold → 不就緒
            _meta("noplan", dispatch="auto", plan=None),  # 無 plan → 不就緒
        ]
        ready = ready_units(metas, is_satisfied=lambda _id: True)
        self.assertEqual(ready, [])

    def test_depends_on_gates_readiness(self) -> None:
        from paulshaclaw.coordinator.autonomy import ready_units

        metas = [
            _meta("free", depends_on=[]),                  # 無相依 → 就緒
            _meta("blocked", depends_on=["upstream"]),     # 相依未滿足 → 不就緒
        ]
        # upstream 未滿足
        ready = ready_units(metas, is_satisfied=lambda _id: _id != "upstream")
        self.assertEqual([m["slice_id"] for m in ready], ["free"])

        # upstream 滿足 → blocked 釋放；確定性序（沿 metas 順序：free 在前、blocked 在後）
        ready2 = ready_units(metas, is_satisfied=lambda _id: True)
        self.assertEqual([m["slice_id"] for m in ready2], ["free", "blocked"])

    def test_default_is_satisfied_reads_gate_status(self) -> None:
        from paulshaclaw.coordinator.autonomy import default_is_satisfied

        with tempfile.TemporaryDirectory() as d:
            hd = Path(d) / "handoff"
            hd.mkdir()
            (hd / "passed-slice.json").write_text(
                json.dumps({"gate_status": "passed"}), encoding="utf-8"
            )
            (hd / "failed-slice.json").write_text(
                json.dumps({"gate_status": "failed"}), encoding="utf-8"
            )
            self.assertTrue(default_is_satisfied("passed-slice", handoff_dir=str(hd)))
            self.assertFalse(default_is_satisfied("failed-slice", handoff_dir=str(hd)))
            self.assertFalse(default_is_satisfied("missing-slice", handoff_dir=str(hd)))


# --------------------------------------------------------------------------- #
# FanoutTests
# --------------------------------------------------------------------------- #
class FanoutTests(unittest.TestCase):
    def test_dispatch_ready_dispatches_exactly_ready_set(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready

        metas = [
            _meta("ready-1", depends_on=[]),
            _meta("held", dispatch="hold"),
            _meta("noplan", dispatch="auto", plan=None),
            _meta("blocked", depends_on=["down"]),     # down 未滿足 → 不就緒
            _meta("ready-2", depends_on=["up"]),        # up 滿足 → 就緒
        ]
        fake = _FakeDispatcher()
        # is_satisfied 只對 "up" 回 True → ready-1（無相依）、ready-2（dep=up）就緒；
        # held（hold）/noplan（無 plan）/blocked（dep=down 未滿足）皆不就緒
        jobs = dispatch_ready(
            metas,
            is_satisfied=lambda _id: _id == "up",
            dispatcher=fake,
            persona="builder",
        )
        dispatched_tasks = [c["task"] for c in fake.calls]
        self.assertEqual(sorted(dispatched_tasks), ["ready-1", "ready-2"])
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(c["persona"] == "builder" for c in fake.calls))
        # 非就緒一個都沒派
        self.assertNotIn("held", dispatched_tasks)
        self.assertNotIn("noplan", dispatched_tasks)
        self.assertNotIn("blocked", dispatched_tasks)

    def test_dispatch_ready_with_real_dispatcher_fake_seams(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready
        from paulshaclaw.coordinator.dispatcher import Dispatcher
        from paulshaclaw.coordinator.registry import JobRegistry

        class _FakeSender:
            def __init__(self):
                self.sent = []

            def send(self, pane_id, text):
                self.sent.append((pane_id, text))

        class _FakeWt:
            def create(self, branch):
                return f"/fake/wt/{branch.replace('/', '-')}"

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            sender = _FakeSender()
            disp = Dispatcher(reg, sender, _FakeWt())
            metas = [_meta("real-a", depends_on=[]), _meta("real-b", depends_on=[])]
            jobs = dispatch_ready(
                metas,
                is_satisfied=lambda _id: True,
                dispatcher=disp,
                # git_runner 取不到 head → dispatch_head=None（不碰真 git）
            )
            self.assertEqual(len(jobs), 2)
            self.assertEqual({j["status"] for j in jobs}, {"dispatched"})
            self.assertEqual(len(reg.list_jobs()), 2)
            # 各自一個 pane（fan-out 佔位 %0、%1...）
            self.assertEqual(len(sender.sent), 2)
            self.assertNotEqual(sender.sent[0][0], sender.sent[1][0])


# --------------------------------------------------------------------------- #
# CliTests
# --------------------------------------------------------------------------- #
class CliTests(unittest.TestCase):
    def test_main_ready_lists_ready_units(self) -> None:
        from paulshaclaw.coordinator.cli import main

        with tempfile.TemporaryDirectory() as d:
            _write_spec(Path(d), "r.md", "dispatch: auto\nslice_id: r\nplan: docs/p.md")
            _write_spec(Path(d), "h.md", "dispatch: hold\nslice_id: h")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["ready", "--specs-dir", d], is_satisfied=lambda _id: True)
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual([m["slice_id"] for m in payload], ["r"])

    def test_main_fanout_with_fakes(self) -> None:
        from paulshaclaw.coordinator.cli import main
        from paulshaclaw.coordinator.registry import JobRegistry

        class _FakeSender:
            def __init__(self):
                self.sent = []

            def send(self, pane_id, text):
                self.sent.append((pane_id, text))

        class _FakeWt:
            def create(self, branch):
                return f"/fake/wt/{branch.replace('/', '-')}"

        with tempfile.TemporaryDirectory() as d:
            _write_spec(Path(d), "a.md", "dispatch: auto\nslice_id: fa\nplan: docs/p.md")
            _write_spec(Path(d), "b.md", "dispatch: auto\nslice_id: fb\nplan: docs/p.md\ndepends_on: [up]")
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            sender = _FakeSender()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(
                    ["fanout", "--specs-dir", d],
                    registry=reg,
                    pane_sender=sender,
                    worktree_creator=_FakeWt(),
                    is_satisfied=lambda _id: True,  # up 滿足 → fa, fb 都就緒
                )
            self.assertEqual(rc, 0)
            jobs = json.loads(out.getvalue())
            self.assertEqual(sorted(j["task"] for j in jobs), ["fa", "fb"])
            self.assertEqual(len(reg.list_jobs()), 2)
            self.assertEqual(len(sender.sent), 2)  # 不碰真 tmux/copilot

    def test_main_refuses_on_cycle(self) -> None:
        from paulshaclaw.coordinator.cli import main

        with tempfile.TemporaryDirectory() as d:
            _write_spec(Path(d), "a.md", "dispatch: auto\nslice_id: A\nplan: p\ndepends_on: [B]")
            _write_spec(Path(d), "b.md", "dispatch: auto\nslice_id: B\nplan: p\ndepends_on: [A]")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = main(["ready", "--specs-dir", d], is_satisfied=lambda _id: True)
            self.assertNotEqual(rc, 0)  # refuse
            self.assertIn("循環", err.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
```

- [ ] 2.1 寫入上述測試檔
- [ ] 2.2 `python -m unittest tests.test_persona_phase4_fanout_autonomy -v` → 確認 RED 為「`ModuleNotFoundError: paulshaclaw.coordinator.autonomy`」或缺屬性（**預期** RED；非語法錯）
- [ ] 2.3 捕捉 RED 輸出為證據

---

## Task 3 — GREEN：新增 `paulshaclaw/coordinator/autonomy.py`

以下為**完整模組內容**（無 placeholder）：

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import yaml

# is_satisfied predicate 型別：收 slice_id，回該相依是否「已滿足」（可釋放下游）。
# 判定來源由呼叫者決定（merged-to-main vs handoff gate_status）——#104 留開放。
IsSatisfied = Callable[[str], bool]

# Dispatcher duck-type：只需有 dispatch(task, persona, pane_id, command) -> dict（Phase 2 介面）。
DEFAULT_HANDOFF_DIR = "runtime/handoff"


# --------------------------------------------------------------------------- #
# 1) frontmatter 解析（預設 HOLD）
# --------------------------------------------------------------------------- #
def _split_frontmatter(text: str) -> str | None:
    """回 frontmatter 區塊原文；無合法 frontmatter（不以 --- 起頭/無收尾 ---）→ None。"""
    if not text.startswith("---"):
        return None
    # 首行 --- 之後找下一個單獨成行的 ---
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return None  # 無收尾 ---


def parse_spec_frontmatter(path) -> dict:
    """解析 superpowers spec 開頭 --- frontmatter。

    回 {path, dispatch, slice_id, plan, depends_on}。
    硬約束：dispatch 僅在字面值為 'auto' 時為 'auto'，其餘一律 'hold'（fail-safe）。
    容忍無 frontmatter（視為 hold），不 raise。
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    block = _split_frontmatter(text)

    meta: dict = {
        "path": str(p),
        "dispatch": "hold",
        "slice_id": None,
        "plan": None,
        "depends_on": [],
    }
    if block is None:
        return meta

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return meta  # 壞 frontmatter → 視為 hold（fail-safe，不 raise）
    if not isinstance(data, dict):
        return meta

    # dispatch：只認字面 'auto'
    if data.get("dispatch") == "auto":
        meta["dispatch"] = "auto"

    sid = data.get("slice_id")
    meta["slice_id"] = sid if isinstance(sid, str) else None

    plan = data.get("plan")
    meta["plan"] = plan if isinstance(plan, str) else None

    dep = data.get("depends_on")
    if isinstance(dep, list):
        meta["depends_on"] = [str(x) for x in dep]
    elif isinstance(dep, str):
        meta["depends_on"] = [dep]  # 單一字串容錯成單元素 list
    else:
        meta["depends_on"] = []

    return meta


# --------------------------------------------------------------------------- #
# 2) scan_specs（確定性）
# --------------------------------------------------------------------------- #
def scan_specs(specs_dir) -> list[dict]:
    """掃 specs_dir 下 *.md，逐檔 parse_spec_frontmatter，確定性排序。

    目錄不存在 → []（非錯誤）。
    """
    d = Path(specs_dir)
    if not d.is_dir():
        return []
    return [parse_spec_frontmatter(p) for p in sorted(d.glob("*.md"))]


# --------------------------------------------------------------------------- #
# 3) detect_cycles（DAG 回邊偵測，refuse）
# --------------------------------------------------------------------------- #
def detect_cycles(metas: list[dict]) -> None:
    """以 slice_id 為節點、depends_on 為有向邊偵測循環相依。

    成環 → raise ValueError（帶 cycle path）。
    指向不在 metas 的 slice_id 的邊不算環（外部/未掃到，交給 is_satisfied）。
    """
    graph: dict[str, list[str]] = {}
    for m in metas:
        sid = m.get("slice_id")
        if isinstance(sid, str):
            graph[sid] = [d for d in m.get("depends_on", [])]

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in graph}
    stack: list[str] = []

    def visit(node: str) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                continue  # 外部相依 → 不算環
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise ValueError(f"depends_on 偵測到循環相依: {' -> '.join(cycle)}")
            if color[dep] == WHITE:
                visit(dep)
        stack.pop()
        color[node] = BLACK

    for sid in graph:
        if color[sid] == WHITE:
            visit(sid)


# --------------------------------------------------------------------------- #
# 4) ready_units（三條件 + 先偵測環）
# --------------------------------------------------------------------------- #
def ready_units(metas: list[dict], is_satisfied: IsSatisfied) -> list[dict]:
    """回就緒單位：dispatch=='auto' ∧ plan 非空 ∧ depends_on 全滿足。

    MUST 先 detect_cycles（成環整批 raise，不回部分集）。
    is_satisfied 為必注入參數（呼叫者決定判定來源）。確定性序（沿 metas 順序）。
    """
    detect_cycles(metas)  # 先 refuse 環
    ready: list[dict] = []
    for m in metas:
        if m.get("dispatch") != "auto":
            continue
        if not (isinstance(m.get("plan"), str) and m["plan"]):
            continue
        deps = m.get("depends_on", [])
        if all(is_satisfied(dep) for dep in deps):
            ready.append(m)
    return ready


# --------------------------------------------------------------------------- #
# 5) default_is_satisfied（預設來源 = handoff gate_status；保持可注入覆寫）
# --------------------------------------------------------------------------- #
def default_is_satisfied(slice_id: str, handoff_dir: str = DEFAULT_HANDOFF_DIR) -> bool:
    """預設判定：runtime/handoff/<slice_id>.json 存在且 gate_status=='passed'。

    檔不存在/壞檔/非 passed → False（fail-closed：未證明滿足即不釋放下游）。
    這只是預設 impl；ready_units/dispatch_ready 一律收注入 predicate，
    未來換 merged-to-main 來源只需換注入物（同 Callable[[str], bool] 介面）。
    """
    p = Path(handoff_dir) / f"{slice_id}.json"
    if not p.is_file():
        return False
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(payload, dict) and payload.get("gate_status") == "passed"


# --------------------------------------------------------------------------- #
# 6) dispatch_ready（fan-out，reuse Phase 2 Dispatcher）
# --------------------------------------------------------------------------- #
def dispatch_ready(
    metas: list[dict],
    is_satisfied: IsSatisfied,
    dispatcher,
    persona: str = "builder",
) -> list[dict]:
    """算就緒集，對每單位經注入的 Phase 2 Dispatcher 各派一筆 job（reuse，不重寫派工）。

    一單位一 job；隔離靠 per-worktree/pane（Phase 2 性質），故並行安全。
    pane_id/command 為佔位（真實 pane 分配與 copilot prompt 拼裝屬 §5 ①，非本層）。
    回 dispatched jobs。
    """
    ready = ready_units(metas, is_satisfied)
    jobs: list[dict] = []
    for i, m in enumerate(ready):
        slice_id = m["slice_id"]
        job = dispatcher.dispatch(
            task=slice_id,
            persona=persona,
            pane_id=f"%{i}",
            command=f"# dispatch {slice_id} (plan={m['plan']})",
        )
        jobs.append(job)
    return jobs
```

- [ ] 3.1 寫入上述 `autonomy.py`
- [ ] 3.2 `python -m unittest tests.test_persona_phase4_fanout_autonomy.FrontmatterTests tests.test_persona_phase4_fanout_autonomy.ScanTests tests.test_persona_phase4_fanout_autonomy.CycleTests tests.test_persona_phase4_fanout_autonomy.ReadyTests tests.test_persona_phase4_fanout_autonomy.FanoutTests -v` → GREEN

---

## Task 4 — GREEN：擴充 `paulshaclaw/coordinator/cli.py`（ready / fanout）

對既有 `cli.py` 做最小 diff——**保留 `dispatch`/`jobs`/`stat` 不動**，只加子命令與 `is_satisfied` 注入點。

### 4.1 `_build_parser` 新增兩個子命令（在 `p_stat` 之後）

```python
    p_ready = sub.add_parser("ready", help="列出就緒（dispatch:auto∧有plan∧depends_on全滿足）的單位")
    p_ready.add_argument("--specs-dir", required=True)

    p_fanout = sub.add_parser("fanout", help="對就緒集經 Dispatcher 並行派工")
    p_fanout.add_argument("--specs-dir", required=True)
    p_fanout.add_argument("--persona", default="builder")
```

### 4.2 `main` 簽名加 `is_satisfied` 並處理新子命令

`main` 簽名改為：

```python
def main(
    argv: Sequence[str] | None = None,
    *,
    registry: JobRegistry | None = None,
    pane_sender: PaneSender | None = None,
    worktree_creator: WorktreeCreator | None = None,
    is_satisfied=None,
) -> int:
```

於檔頭新增 import：

```python
from . import autonomy
```

在現有 `dispatch`/`jobs`/`stat` 分支「之後、`return 2` 之前」插入：

```python
    if args.cmd in ("ready", "fanout"):
        predicate = is_satisfied if is_satisfied is not None else autonomy.default_is_satisfied
        metas = autonomy.scan_specs(args.specs_dir)
        try:
            if args.cmd == "ready":
                ready = autonomy.ready_units(metas, predicate)
                print(json.dumps(ready, ensure_ascii=False))
                return 0
            # fanout：reuse Phase 2 Dispatcher（注入或預設 seam）
            disp = Dispatcher(reg, sender, creator)
            jobs = autonomy.dispatch_ready(metas, predicate, disp, persona=args.persona)
            print(json.dumps(jobs, ensure_ascii=False))
            return 0
        except ValueError as exc:        # 循環相依 → refuse
            print(f"錯誤: {exc}", file=sys.stderr)
            return 1
```

> 註：`reg`/`sender`/`creator` 為既有 `main` 內已實體化的三 seam（未注入時接真實作）。`fanout` 用它們組 `Dispatcher`，與 `dispatch` 子命令同源；測試一律全注入 fake。`ready` 不需 seam（純算就緒集），但 `main` 開頭仍會實體化它們——測試傳 fake 即可，不碰真 tmux/git。

- [ ] 4.3 套用上述 diff（最小變更，不動既有子命令邏輯）
- [ ] 4.4 `python -m unittest tests.test_persona_phase4_fanout_autonomy.CliTests -v` → GREEN

---

## Task 5 — 匯出 + 不回歸 + scope 紀律

### 5.1 `paulshaclaw/coordinator/__init__.py` 加入 `autonomy`

```python
from . import autonomy, cli, dispatcher, registry, seams

__all__ = [
    "registry",
    "seams",
    "dispatcher",
    "cli",
    "autonomy",
]
```

- [ ] 5.2 確認 `git diff --name-only` **不含** `paulshaclaw/core/daemon.py`、`paulshaclaw/core/config.py`
- [ ] 5.3 確認 `git diff` **未改** `paulshaclaw/coordinator/{dispatcher,registry,seams}.py`（reuse Phase 2）
- [ ] 5.4 `python -m unittest tests.test_persona_phase4_fanout_autonomy -v` 全綠
- [ ] 5.5 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q`：僅可接受 2 個 stage11 textual `query_one` 失敗；若 `test_hooks.py`/`test_importer_cli.py`/`test_skillopt_loop.py` 偶發 flake → 單獨重跑確認綠（known flake，非本 change）
- [ ] 5.6 `openspec validate persona-phase4-fanout-autonomy --strict` 通過

---

## Verification（完工前最後核對）

- [ ] V1 預設 HOLD：無 `dispatch: auto`/無 frontmatter 的 spec 不就緒、不被派工
- [ ] V2 循環相依：`ready`/`fanout`/`ready_units` 對成環 metas raise/exit 非零，不派任何工
- [ ] V3 depends_on gate：未滿足不就緒、滿足才釋放；`is_satisfied` 為注入點（`default_is_satisfied` 僅後援）
- [ ] V4 reuse Phase 2 Dispatcher：`dispatch_ready` 僅呼 `Dispatcher.dispatch`；未改 dispatcher/registry/seams
- [ ] V5 fakes-only：所有測試以 fake dispatcher 或真 `Dispatcher`+fake seam，無真 copilot/tmux/git
- [ ] V6 scope：未改 `core/daemon.py`/`core/config.py`
- [ ] V7 全套件不回歸（僅既知 stage11 textual 2 筆）；`openspec validate --strict` 綠

---

## Commits

> 本 plan 任務（docs-only）僅一個 commit；實作階段另起 commits（每 GREEN 一個 conventional commit）。

**Docs commit（本任務）:**

```
docs(stage4): persona Phase 4 fan-out + autonomy + depends_on DAG change 與 TDD plan (#104)

新增 openspec change persona-phase4-fanout-autonomy（proposal/design/specs/tasks，
modify capability coordinator-cli）與 docs/superpowers/plans/2026-06-18-persona-phase4-fanout-autonomy.md。
涵蓋設計 §9 manager fan-out + autonomy gate 與 issue #104 depends_on DAG：
frontmatter 預設 HOLD、循環相依 refuse、就緒判定（pluggable is_satisfied）、
reuse Phase 2 Dispatcher 的 fan-out、ready/fanout CLI 子命令。openspec validate --strict 綠。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

**實作階段 commits（後續，非本任務）:**

- `test(stage4): persona Phase 4 fan-out/autonomy/DAG RED 測試` — Task 2
- `feat(stage4): autonomy.py — frontmatter 解析(預設HOLD)/scan/DAG/ready/fan-out` — Task 3
- `feat(stage4): coordinator CLI 加 ready/fanout 子命令（reuse Phase 2 Dispatcher）` — Task 4
