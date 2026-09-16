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
            spec = specs_by_key[group.key]
            header_text = "".join(text for text, _ in spec.segments)
            self.assertFalse(spec.expand)
            self.assertTrue(spec.children)
            self.assertIn("最近完成", header_text)
            self.assertIn(f"{len(group.rows)} 已完成", header_text)
            child_text = "".join(text for text, _ in spec.children[0].segments)
            self.assertIn("已完成", child_text)
            self.assertNotIn("passed", child_text)

    def test_recent_done_history_is_excluded_from_jobs_count(self) -> None:
        rows = slices_from_status(_recent_done_status_fixture())

        self.assertEqual(jobs_counts_summary(rows), "3 件 · 2 不可認領")

    def test_recent_done_history_maps_unknown_gate_status_to_finished_label(self) -> None:
        groups = group_job_rows(
            slices_from_status(
                {
                    "degraded": False,
                    "recent_done": [
                        {
                            "slice_id": "wf-history-unknown-verification",
                            "gate_status": "mystery-finished-state",
                        }
                    ],
                }
            ),
            axis="project",
        )

        (spec,) = build_jobs_nodes(groups, axis="project")
        header_text = "".join(text for text, _ in spec.segments)
        child_text = "".join(text for text, _ in spec.children[0].segments)

        self.assertIn("1 已結束", header_text)
        self.assertNotIn("1 已完成", header_text)
        self.assertIn("已結束", child_text)
        self.assertNotIn("mystery-finished-state", child_text)

    def test_recent_done_history_preserves_pending_decision_summary_in_collapsed_header(
        self,
    ) -> None:
        groups = group_job_rows(
            slices_from_status(
                {
                    "degraded": False,
                    "recent_done": [
                        {
                            "slice_id": "wf-e13fa4daae-subagent-build",
                            "gate_status": "needs_human",
                        },
                        {
                            "slice_id": "wf-e13fa4daae-code-review",
                            "gate_status": "needs_human",
                        },
                        {
                            "slice_id": "wf-e13fa4daae-verification",
                            "gate_status": "needs_human",
                        },
                    ],
                }
            ),
            axis="project",
        )

        (spec,) = build_jobs_nodes(groups, axis="project")
        header_text = "".join(text for text, _ in spec.segments)

        self.assertIn("最近完成", header_text)
        self.assertIn("3 phase 全待裁決", header_text)
        self.assertNotIn("3 已完成", header_text)

    def test_recent_done_history_omits_terminal_run_status_rows(self) -> None:
        rows = slices_from_status(
            {
                "degraded": False,
                "recent_done": [
                    {"slice_id": "wf-history-keep-build", "gate_status": "passed"},
                    {
                        "slice_id": "wf-history-drop-done-build",
                        "gate_status": "passed",
                        "run_status": "done",
                    },
                    {
                        "slice_id": "wf-history-drop-superseded-build",
                        "gate_status": "passed",
                        "run_status": "superseded",
                    },
                    {
                        "slice_id": "wf-history-keep-unknown-build",
                        "gate_status": "passed",
                        "run_status": "archived",
                    },
                ],
            }
        )

        self.assertEqual(
            [row.slice_id for row in rows],
            ["wf-history-keep-build", "wf-history-keep-unknown-build"],
        )
