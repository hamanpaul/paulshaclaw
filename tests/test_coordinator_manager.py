from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paulshaclaw.coordinator import manager
from paulshaclaw.coordinator.registry import JobRegistry


class FakeDispatcher:
    """包真 JobRegistry；poll_headless_done 依 poll_map 腳本化轉態。"""

    def __init__(self, registry: JobRegistry, poll_map: dict | None = None,
                 raise_on: set | None = None) -> None:
        self._registry = registry
        self._poll_map = poll_map or {}   # job_id -> "done"/"failed"
        self._raise_on = raise_on or set()  # job_id -> 模擬 poll 例外

    def poll_headless_done(self, job_id: str) -> dict:
        if job_id in self._raise_on:
            raise RuntimeError(f"poll 爆炸: {job_id}")
        status = self._poll_map.get(job_id)
        if status is None:
            return self._registry.get_job(job_id)  # 仍在跑
        return self._registry.update_headless_result(
            job_id, status=status, exit_code=0 if status == "done" else 1
        )


def _reg(tmp: str) -> JobRegistry:
    return JobRegistry(state_path=Path(tmp) / "jobs.json")


def _make_job(reg: JobRegistry, slice_id: str) -> dict:
    return reg.create_job(
        task=slice_id, persona="builder", branch=f"feature/{slice_id}",
        pane="", worktree=f"/wt/{slice_id}",
        executor="copilot", session_name=slice_id, pid=4242,
        log_path=f"/logs/{slice_id}.jsonl",
    )


class CompleteTickDoneTests(unittest.TestCase):
    def test_done_job_writes_passed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-a")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"

            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")

            manifest = json.loads((hdir / "slice-a.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "passed")
            self.assertEqual(manifest["completion"], "done")
            self.assertEqual(manifest["slice_id"], "slice-a")
            self.assertEqual(manifest["completed_at"], "T0")
            self.assertEqual(summary["completed"], [{"slice_id": "slice-a", "gate_status": "passed"}])
            self.assertEqual(summary["errors"], [])


class CompleteTickFailedAndInFlightTests(unittest.TestCase):
    def test_failed_job_writes_failed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-b")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "failed"})
            hdir = Path(d) / "handoff"
            manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
            manifest = json.loads((hdir / "slice-b.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "failed")
            self.assertEqual(manifest["completion"], "failed")

    def test_in_flight_job_not_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-c")
            disp = FakeDispatcher(reg, poll_map={})
            hdir = Path(d) / "handoff"
            summary = manager.complete_tick(disp, handoff_dir=str(hdir))
            self.assertFalse((hdir / "slice-c.json").exists())
            self.assertEqual(summary["completed"], [])
            self.assertIn(job["job_id"], summary["polled"])


class CompleteTickReconcileTests(unittest.TestCase):
    def test_terminal_job_missing_manifest_is_reconciled(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-d")
            reg.update_headless_result(job["job_id"], status="done", exit_code=0)
            disp = FakeDispatcher(reg, poll_map={})
            hdir = Path(d) / "handoff"
            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
            self.assertTrue((hdir / "slice-d.json").exists())
            self.assertEqual(summary["completed"], [{"slice_id": "slice-d", "gate_status": "passed"}])
            self.assertEqual(summary["polled"], [])

    def test_idempotent_second_tick_no_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-e")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
            second = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T1")
            manifest = json.loads((hdir / "slice-e.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["completed_at"], "T0")
            self.assertEqual(second["completed"], [])
            self.assertEqual(second["polled"], [])


class CompleteTickShadowGateTests(unittest.TestCase):
    def test_shadow_gate_verdict_recorded_but_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-f")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            fake_gate = lambda j: {"ok": False, "violations": [{"path": "x", "reason": "out"}],
                                   "handoff_ok": False}
            manager.complete_tick(disp, gate_runner=fake_gate, handoff_dir=str(hdir), clock=lambda: "T0")
            manifest = json.loads((hdir / "slice-f.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "passed")
            self.assertEqual(manifest["gate_verdict"]["ok"], False)

    def test_gate_runner_exception_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-g")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            def boom(j):
                raise RuntimeError("gate 爆炸")
            manager.complete_tick(disp, gate_runner=boom, handoff_dir=str(hdir), clock=lambda: "T0")
            manifest = json.loads((hdir / "slice-g.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "passed")
            self.assertIsNone(manifest["gate_verdict"])


class CompleteTickErrorAndReleaseTests(unittest.TestCase):
    def test_per_job_poll_error_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            a = _make_job(reg, "slice-h")
            b = _make_job(reg, "slice-i")
            disp = FakeDispatcher(reg, poll_map={b["job_id"]: "done"}, raise_on={a["job_id"]})
            hdir = Path(d) / "handoff"
            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
            self.assertTrue((hdir / "slice-i.json").exists())
            self.assertFalse((hdir / "slice-h.json").exists())
            self.assertEqual(summary["completed"], [{"slice_id": "slice-i", "gate_status": "passed"}])
            self.assertEqual([e["job_id"] for e in summary["errors"]], [a["job_id"]])

    def test_downstream_released_after_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            up = _make_job(reg, "up")
            disp = FakeDispatcher(reg, poll_map={up["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            metas = [
                {"slice_id": "up", "dispatch": "auto", "plan": "p-up.md", "depends_on": []},
                {"slice_id": "down", "dispatch": "auto", "plan": "p-down.md", "depends_on": ["up"]},
            ]
            summary = manager.complete_tick(disp, handoff_dir=str(hdir), metas=metas, clock=lambda: "T0")
            self.assertIn("down", summary["released"])
            from paulshaclaw.coordinator import autonomy
            self.assertTrue(autonomy.default_is_satisfied("up", handoff_dir=str(hdir)))


class CompleteTickGuardTests(unittest.TestCase):
    def test_job_without_valid_slice_id_goes_to_errors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-x")
            # 直接污染 registry 內部 job 的 task 成 None，模擬 corrupt 狀態
            reg._jobs[0]["task"] = None
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
            self.assertFalse((hdir / "None.json").exists())
            self.assertEqual(summary["completed"], [])
            self.assertEqual([e["job_id"] for e in summary["errors"]], [job["job_id"]])

    def test_cyclic_metas_does_not_crash_tick(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "a")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            cyclic = [
                {"slice_id": "a", "dispatch": "auto", "plan": "pa.md", "depends_on": ["b"]},
                {"slice_id": "b", "dispatch": "auto", "plan": "pb.md", "depends_on": ["a"]},
            ]
            summary = manager.complete_tick(disp, handoff_dir=str(hdir), metas=cyclic, clock=lambda: "T0")
            # 完成側仍寫出 manifest；released 因環被停用而省略
            self.assertTrue((hdir / "a.json").exists())
            self.assertEqual(summary["completed"], [{"slice_id": "a", "gate_status": "passed"}])
            self.assertNotIn("released", summary)

    def test_unsafe_slice_id_rejected_no_escape_write(self) -> None:
        for bad in ["../evil", "/abs/evil", "a/b", "..", ".", "x/../y", "with space"]:
            with tempfile.TemporaryDirectory() as d:
                reg = _reg(d)
                job = _make_job(reg, "ok")
                reg._jobs[0]["task"] = bad   # 模擬不安全/corrupt slice_id
                disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
                hdir = Path(d) / "handoff"
                summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
                self.assertEqual(summary["completed"], [], f"{bad!r} 應被拒")
                self.assertEqual([e["job_id"] for e in summary["errors"]], [job["job_id"]])
                # 確認沒有任何檔案被寫到 hdir 外或 hdir 內
                self.assertFalse(hdir.exists() and any(hdir.iterdir()), f"{bad!r} 不應寫出檔案")


if __name__ == "__main__":
    unittest.main()
