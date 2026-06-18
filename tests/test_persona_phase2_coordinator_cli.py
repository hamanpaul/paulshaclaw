from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class JobRegistryTests(unittest.TestCase):
    def test_create_get_update_deterministic_id(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            job1 = reg.create_job(
                task="mytask", persona="builder",
                branch="feature/mytask", pane="%1", worktree="/wt/mytask",
            )
            # 確定性 job_id：task + 單調計數器，非時間/亂數
            self.assertEqual(job1["job_id"], "mytask-1")
            self.assertEqual(job1["task"], "mytask")
            self.assertEqual(job1["persona"], "builder")
            self.assertEqual(job1["branch"], "feature/mytask")
            self.assertEqual(job1["pane"], "%1")
            self.assertEqual(job1["worktree"], "/wt/mytask")
            self.assertEqual(job1["status"], "dispatched")
            self.assertIn("created_at", job1)

            # 同 task 再建 → 單調遞增，不撞號
            job2 = reg.create_job(
                task="mytask", persona="builder",
                branch="feature/mytask-2", pane="%2", worktree="/wt/mytask-2",
            )
            self.assertEqual(job2["job_id"], "mytask-2")

            self.assertEqual(reg.get_job("mytask-1"), job1)
            self.assertEqual(len(reg.list_jobs()), 2)

            updated = reg.update_status("mytask-1", "done")
            self.assertEqual(updated["status"], "done")
            self.assertEqual(reg.get_job("mytask-1")["status"], "done")

    def test_update_status_rejects_unknown(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            reg.create_job(task="t", persona="builder",
                           branch="b", pane="%1", worktree="/wt/t")
            with self.assertRaises(ValueError):
                reg.update_status("t-1", "bogus")        # 非法 status
            with self.assertRaises(KeyError):
                reg.update_status("nope-9", "done")       # 不存在 job

    def test_persistence_round_trip(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "jobs.json"
            reg = JobRegistry(state_path=state)
            reg.create_job(task="alpha", persona="builder",
                           branch="feature/alpha", pane="%3", worktree="/wt/alpha")
            # 新 registry 指向同一檔 → 讀回
            reg2 = JobRegistry(state_path=state)
            jobs = reg2.list_jobs()
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["job_id"], "alpha-1")
            self.assertEqual(reg2.get_job("alpha-1")["worktree"], "/wt/alpha")
            # 重載後新 job 續編、不撞號
            job_b = reg2.create_job(task="alpha", persona="builder",
                                    branch="feature/alpha-b", pane="%4", worktree="/wt/alpha-b")
            self.assertEqual(job_b["job_id"], "alpha-2")

    def test_corrupt_state_fails_closed(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "jobs.json"
            state.write_text("{ this is not valid json", encoding="utf-8")
            with self.assertRaises(ValueError):
                JobRegistry(state_path=state)   # fail-closed：不可靜默清空

    def test_missing_state_is_empty_registry(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "absent.json")
            self.assertEqual(reg.list_jobs(), [])   # 不存在非錯誤


# ---- fakes（dispatcher / cli 測試共用；真實作不進任何測試）----
class FakePaneSender:
    """記錄 send 呼叫的 fake；結構相容 seams.PaneSender。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, pane_id: str, text: str) -> None:
        self.sent.append((pane_id, text))


class FakeWorktreeCreator:
    """回固定路徑並記錄 branch 的 fake；結構相容 seams.WorktreeCreator。"""

    def __init__(self, root: str = "/fake/wt") -> None:
        self.root = root
        self.created: list[str] = []

    def create(self, branch: str) -> str:
        self.created.append(branch)
        return f"{self.root}/{branch.replace('/', '-')}"


class SeamProtocolTests(unittest.TestCase):
    def test_fakes_satisfy_protocols(self) -> None:
        from paulshaclaw.coordinator import seams

        sender: seams.PaneSender = FakePaneSender()
        creator: seams.WorktreeCreator = FakeWorktreeCreator()
        sender.send("%9", "hello")
        path = creator.create("feature/x")
        self.assertEqual(path, "/fake/wt/feature-x")
        # 真實作存在且為對應型別（不呼叫其副作用方法）
        self.assertTrue(hasattr(seams, "TmuxPaneSender"))
        self.assertTrue(hasattr(seams, "ScriptWorktreeCreator"))


if __name__ == "__main__":
    unittest.main()
