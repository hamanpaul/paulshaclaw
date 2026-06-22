from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paulshaclaw.coordinator.completion import classify_completion
from paulshaclaw.coordinator.registry import JobRegistry


class CompletionTests(unittest.TestCase):
    def test_exit0_with_success_jsonl_is_done(self) -> None:
        self.assertEqual(
            classify_completion(exit_code=0, last_jsonl_line='{"type":"result","ok":true}'),
            "done",
        )

    def test_nonzero_exit_is_failed(self) -> None:
        self.assertEqual(classify_completion(exit_code=1, last_jsonl_line=None), "failed")

    def test_unparseable_jsonl_fallbacks_to_exit_code(self) -> None:
        self.assertEqual(classify_completion(exit_code=0, last_jsonl_line="not json"), "done")
        self.assertEqual(classify_completion(exit_code=2, last_jsonl_line="not json"), "failed")


class HeadlessRegistryFieldsTests(unittest.TestCase):
    def test_create_job_records_headless_session_fields(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            job = reg.create_job(
                task="slice-a",
                persona="builder",
                branch="feature/slice-a",
                pane="%0",
                worktree="/wt/slice-a",
                executor="copilot",
                session_name="slice-a",
                pid=123,
                log_path="/logs/slice-a.jsonl",
                exit_code=0,
            )

            self.assertEqual(job["executor"], "copilot")
            self.assertEqual(job["session_name"], "slice-a")
            self.assertEqual(job["pid"], 123)
            self.assertEqual(job["log_path"], "/logs/slice-a.jsonl")
            self.assertEqual(job["exit_code"], 0)
            self.assertEqual(reg.get_job("slice-a-1")["executor"], "copilot")


if __name__ == "__main__":
    unittest.main()
