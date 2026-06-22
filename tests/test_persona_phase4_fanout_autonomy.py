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

    def test_duplicate_slice_id_refused(self) -> None:
        from paulshaclaw.coordinator.autonomy import detect_cycles, ready_units

        # 重複 slice_id 本身 → 直接 refuse（身分不明確），不靜默以後者覆寫前者的邊
        dup = [_meta("dupX", depends_on=[]), _meta("dupX", depends_on=[])]
        with self.assertRaisesRegex(ValueError, "重複 slice_id"):
            detect_cycles(dup)
        with self.assertRaisesRegex(ValueError, "重複 slice_id"):
            ready_units(dup, is_satisfied=lambda _id: True)

    def test_duplicate_slice_id_does_not_mask_cycle(self) -> None:
        from paulshaclaw.coordinator.autonomy import detect_cycles

        # A->B, A->[], B->A：第二個 A 不得覆寫掉 A->B 而遮蔽 A<->B 真環
        masking = [
            _meta("A", depends_on=["B"]),
            _meta("A", depends_on=[]),
            _meta("B", depends_on=["A"]),
        ]
        with self.assertRaises(ValueError):  # 重複 slice_id 先擋下（亦不漏環）
            detect_cycles(masking)


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

    def test_no_slice_id_not_ready(self) -> None:
        from paulshaclaw.coordinator.autonomy import ready_units

        # auto + 有 plan 但 slice_id 缺（None/空字串）→ 無身分 → MUST NOT 就緒
        metas = [
            {"path": "/s/x.md", "dispatch": "auto", "slice_id": None,
             "plan": "docs/p.md", "depends_on": []},
            {"path": "/s/y.md", "dispatch": "auto", "slice_id": "",
             "plan": "docs/p.md", "depends_on": []},
        ]
        self.assertEqual(ready_units(metas, is_satisfied=lambda _id: True), [])

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
        self.assertNotIn("copilot", command)               # executor wrapping moved to launcher

    def test_dispatch_ready_launches_via_agent_launcher(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready

        calls = []

        class _FakeLauncher:
            def launch(self, *, slice_id, prompt, worktree, log_dir):
                calls.append({"slice_id": slice_id, "prompt": prompt, "worktree": worktree})
                from paulshaclaw.coordinator.launcher import LaunchHandle
                return LaunchHandle(executor="copilot", session_name=slice_id, pid=123, log_path=f"{log_dir}/x")

        metas = [_meta("slice-a", plan="docs/p.md")]
        dispatch_ready(
            metas, is_satisfied=lambda _id: True, dispatcher=_FakeDispatcher(),
            persona="builder", launcher=_FakeLauncher(),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["slice_id"], "slice-a")
        self.assertIn("[PERSONA CONTRACT", calls[0]["prompt"])
        self.assertIn("docs/p.md", calls[0]["prompt"])

    def test_dispatch_ready_launcher_records_headless_job_without_pane_send(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready
        from paulshaclaw.coordinator.dispatcher import Dispatcher
        from paulshaclaw.coordinator.launcher import LaunchHandle
        from paulshaclaw.coordinator.registry import JobRegistry

        class _FakeSender:
            def __init__(self):
                self.sent = []

            def send(self, pane_id, text):
                self.sent.append((pane_id, text))

        class _FakeWt:
            def __init__(self):
                self.created = []

            def create(self, branch):
                self.created.append(branch)
                return f"/fake/wt/{branch.replace('/', '-')}"

        class _FakeLauncher:
            def __init__(self):
                self.calls = []

            def launch(self, *, slice_id, prompt, worktree, log_dir):
                self.calls.append({"slice_id": slice_id, "worktree": worktree, "log_dir": log_dir})
                return LaunchHandle(executor="copilot", session_name=slice_id, pid=123, log_path=f"{log_dir}/x")

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            sender = _FakeSender()
            wt = _FakeWt()
            launcher = _FakeLauncher()
            disp = Dispatcher(reg, sender, wt)
            jobs = dispatch_ready(
                [_meta("slice-a", plan="docs/p.md")],
                is_satisfied=lambda _id: True,
                dispatcher=disp,
                persona="builder",
                launcher=launcher,
            )

            self.assertEqual(sender.sent, [])
            self.assertEqual(wt.created, ["feature/slice-a"])
            self.assertEqual(launcher.calls[0]["worktree"], "/fake/wt/feature-slice-a")
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["executor"], "copilot")
            self.assertEqual(reg.get_job("slice-a-1")["pid"], 123)

    def test_dispatch_ready_launcher_failure_does_not_block_other_slices(self) -> None:
        from paulshaclaw.coordinator.autonomy import DispatchReadyError, dispatch_ready
        from paulshaclaw.coordinator.dispatcher import Dispatcher
        from paulshaclaw.coordinator.launcher import LaunchHandle
        from paulshaclaw.coordinator.registry import JobRegistry

        class _FakeSender:
            def send(self, pane_id, text):
                raise AssertionError("launcher path must not send to pane")

        class _FakeWt:
            def create(self, branch):
                return f"/fake/wt/{branch.replace('/', '-')}"

        class _FailFirstLauncher:
            def __init__(self):
                self.calls = []

            def launch(self, *, slice_id, prompt, worktree, log_dir):
                self.calls.append(slice_id)
                if slice_id == "slice-a":
                    raise RuntimeError("executor missing")
                return LaunchHandle(executor="copilot", session_name=slice_id, pid=123, log_path=f"{log_dir}/x")

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            launcher = _FailFirstLauncher()
            disp = Dispatcher(reg, _FakeSender(), _FakeWt())
            with self.assertRaises(DispatchReadyError) as ctx:
                dispatch_ready(
                    [_meta("slice-a", plan="docs/a.md"), _meta("slice-b", plan="docs/b.md")],
                    is_satisfied=lambda _id: True,
                    dispatcher=disp,
                    persona="builder",
                    launcher=launcher,
                )

            self.assertEqual(launcher.calls, ["slice-a", "slice-b"])
            self.assertEqual([job["task"] for job in ctx.exception.jobs], ["slice-b"])
            self.assertEqual([job["task"] for job in reg.list_jobs()], ["slice-b"])
            self.assertIn("slice-a", str(ctx.exception))

    def test_dispatch_ready_no_slice_id_not_dispatched(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready

        # auto + plan 但無 slice_id → 不就緒 → 不得以 task=None 派工（branch feature/None）
        metas = [
            {"path": "/s/x.md", "dispatch": "auto", "slice_id": None,
             "plan": "docs/p.md", "depends_on": []},
        ]
        fake = _FakeDispatcher()
        jobs = dispatch_ready(metas, is_satisfied=lambda _id: True, dispatcher=fake)
        self.assertEqual(jobs, [])
        self.assertEqual(fake.calls, [])

    def test_dispatch_ready_refuses_duplicate_slice_id(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready

        # 兩份 spec 誤用同一 slice_id → refuse（否則對同一 feature/<id> 重複派工）
        dup = [_meta("dupX", depends_on=[]), _meta("dupX", depends_on=[])]
        fake = _FakeDispatcher()
        with self.assertRaisesRegex(ValueError, "重複 slice_id"):
            dispatch_ready(dup, is_satisfied=lambda _id: True, dispatcher=fake)
        self.assertEqual(fake.calls, [])  # refuse → 一筆都沒派

    def test_dispatch_ready_with_real_dispatcher_fake_seams(self) -> None:
        import subprocess as _subprocess

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

        class _FakeGitRunner:
            """fake git_runner：記錄 rev-parse 呼叫、回固定 head；全程不啟動真 git。"""

            def __init__(self):
                self.calls = []

            def __call__(self, args):
                self.calls.append(list(args))
                return "deadbeef"  # 固定 baseline head

        # spy 真 subprocess.run：本測試全程不得對 git 起任何真子行程
        real_calls: list = []
        orig_run = _subprocess.run

        def _spy_run(args, *a, **k):
            if args and args[0] == "git":
                real_calls.append(list(args))
            return orig_run(args, *a, **k)

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            sender = _FakeSender()
            disp = Dispatcher(reg, sender, _FakeWt())
            git = _FakeGitRunner()
            metas = [_meta("real-a", depends_on=[]), _meta("real-b", depends_on=[])]
            _subprocess.run = _spy_run
            try:
                jobs = dispatch_ready(
                    metas,
                    is_satisfied=lambda _id: True,
                    dispatcher=disp,
                    git_runner=git,  # 注入 fake git_runner → 不 fallback 到真 git
                )
            finally:
                _subprocess.run = orig_run
            self.assertEqual(len(jobs), 2)
            self.assertEqual({j["status"] for j in jobs}, {"dispatched"})
            self.assertEqual(len(reg.list_jobs()), 2)
            # 各自一個 pane（fan-out 佔位 %0、%1...）
            self.assertEqual(len(sender.sent), 2)
            self.assertNotEqual(sender.sent[0][0], sender.sent[1][0])
            # fake git_runner 被各單位呼叫一次（rev-parse feature/<slice>），真 git 零呼叫
            self.assertEqual(
                git.calls,
                [["rev-parse", "feature/real-a"], ["rev-parse", "feature/real-b"]],
            )
            self.assertEqual(real_calls, [])  # 全程不啟動真 git


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
        import subprocess as _subprocess

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

        def _fake_git(args):  # fake git_runner：不啟動真 git
            return "deadbeef"

        real_calls: list = []
        orig_run = _subprocess.run

        def _spy_run(args, *a, **k):
            if args and args[0] == "git":
                real_calls.append(list(args))
            return orig_run(args, *a, **k)

        with tempfile.TemporaryDirectory() as d:
            _write_spec(Path(d), "a.md", "dispatch: auto\nslice_id: fa\nplan: docs/p.md")
            _write_spec(Path(d), "b.md", "dispatch: auto\nslice_id: fb\nplan: docs/p.md\ndepends_on: [up]")
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            sender = _FakeSender()
            out = io.StringIO()
            _subprocess.run = _spy_run
            try:
                with contextlib.redirect_stdout(out):
                    rc = main(
                        ["fanout", "--specs-dir", d],
                        registry=reg,
                        pane_sender=sender,
                        worktree_creator=_FakeWt(),
                        is_satisfied=lambda _id: True,  # up 滿足 → fa, fb 都就緒
                        git_runner=_fake_git,           # 注入 fake → 不碰真 git
                    )
            finally:
                _subprocess.run = orig_run
            self.assertEqual(rc, 0)
            jobs = json.loads(out.getvalue())
            self.assertEqual(sorted(j["task"] for j in jobs), ["fa", "fb"])
            self.assertEqual(len(reg.list_jobs()), 2)
            self.assertEqual(len(sender.sent), 2)  # 不碰真 tmux/copilot
            self.assertEqual(real_calls, [])        # 全程不啟動真 git

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
