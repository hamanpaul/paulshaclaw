"""#369 recent_done history RED regression tests."""

import unittest

from paulshaclaw.cockpit.app import group_job_rows, jobs_counts_summary, slices_from_status
from paulshaclaw.cockpit.jobs_panel import build_jobs_nodes


def _recent_done_status_fixture() -> dict[str, object]:
    return {
        "degraded": False,
        "attention": [
            {
                "slice_id": "add-cortex-version-flag-build",
                "job_state": "exited",
                "reason": "candidate-worktree-dirty",
                "next_actions": ["retry-build"],
            }
        ],
        "recent_done": [
            {
                "slice_id": f"wf-history-{index:02d}-verification",
                "gate_status": "passed",
                "completed_at": f"2026-09-16T05:{index:02d}:00Z",
            }
            for index in range(10)
        ],
        "not_claimable": [
            {"work_id": "needs-issue-1", "detail": "missing_issue"},
            {"work_id": "needs-issue-2", "detail": "missing_issue"},
        ],
    }


class RecentDoneHistoryRedTests(unittest.TestCase):
    def test_recent_done_history_groups_stay_collapsed(self) -> None:
        rows = slices_from_status(_recent_done_status_fixture())
        groups = group_job_rows(rows, axis="project")
        specs_by_key = {spec.key: spec for spec in build_jobs_nodes(groups, axis="project")}

        recent_done_groups = [
            group
            for group in groups
            if group.rows and all(row.source_section == "recent_done" for row in group.rows)
        ]

        self.assertTrue(recent_done_groups)
        for group in recent_done_groups:
            self.assertFalse(specs_by_key[group.key].expand)

    def test_recent_done_history_is_excluded_from_jobs_count(self) -> None:
        rows = slices_from_status(_recent_done_status_fixture())

        self.assertEqual(jobs_counts_summary(rows), "3 件 · 2 不可認領")
