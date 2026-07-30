import ast
import inspect
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

# Textual 是 direct runtime dependency；仍保留 guard，讓尚未安裝 package 的
# source-tree 診斷可收集非 UI 測試。CI 的 editable-install smoke 會強制驗證它存在。
try:
    from textual.pilot import Pilot
    from textual.app import App as _TextualApp
    # Pilot is useful, but we need App.run_test to exist for our test harness
    HAS_TEXTUAL = hasattr(_TextualApp, "run_test")
except Exception:  # ModuleNotFoundError or other import-time issues
    Pilot = None  # type: ignore
    HAS_TEXTUAL = False

from paulshaclaw.cockpit.actions import LayoutActionService
from paulshaclaw.cockpit import __main__ as cockpit_main
from paulshaclaw.cockpit.app import (
    REFRESH_INTERVAL_SECONDS,
    SYSMON_INTERVAL_SECONDS,
    CockpitApp,
    format_work_pane_subtitle,
    pane_display_label,
    _JOBS_WIDTH_FALLBACK,
    _display_width,
    _ellipsize_middle,
    _fit_trailer,
    _pad_display,
    group_job_rows,
    slices_from_status,
)
# jobs_panel 是 JOBS 面板的 Tree 化實作（純函式鏈 + widget），本檔的 JOBS 斷言
# 直接對它取值，不再繞經 app.py 的行預算渲染（那套機制已被捲動取代，見 #264 UX 改版）。
from paulshaclaw.cockpit.jobs_panel import build_jobs_nodes


def _flatten_node_text(node) -> str:
    """把單一節點（含子節點）攤成純文字，供內容斷言用——不綁死排版細節。"""
    text = "".join(segment_text for segment_text, _ in node.segments)
    for child in node.children:
        text += "\n" + _flatten_node_text(child)
    return text


def _flatten_nodes(nodes) -> str:
    return "\n".join(_flatten_node_text(node) for node in nodes)
from paulshaclaw.cockpit.help import HelpModal
from paulshaclaw.cockpit.manager_panel import ManagerModal
from paulshaclaw.cockpit.models import JobRow, JobSummary, PaneRecord, SlotAnchor
from paulshaclaw.cockpit.store import CockpitState, choose_startup_slot
from paulshaclaw.cockpit.tmux import (
    TmuxClient,
    _minicom_map,
    _minicom_summary,
    derive_summary,
    parse_list_panes,
)
from paulsha_cortex.control import constants, contract
from paulsha_cortex.coordinator import manager_daemon


def pane_record(
    pane_id: str,
    *,
    session_name: str = "main",
    window_index: str = "0",
    title: str = "pane",
    command: str = "bash",
    left: int = 0,
    top: int = 0,
    width: int = 80,
    height: int = 24,
    active: bool = False,
    pane_tty: str = "",
    pane_current_path: str = "",
    host_short: str = "",
    summary: str = "",
) -> PaneRecord:
    return PaneRecord(
        pane_id=pane_id,
        session_name=session_name,
        window_index=window_index,
        title=title,
        command=command,
        left=left,
        top=top,
        width=width,
        height=height,
        active=active,
        pane_tty=pane_tty,
        pane_current_path=pane_current_path,
        host_short=host_short,
        summary=summary,
    )


class Stage11CliTests(unittest.TestCase):
    def test_stage11_module_help_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "paulshaclaw.cockpit", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("Stage 11 operator cockpit", completed.stdout)
        self.assertIn("--cockpit-pane", completed.stdout)
        self.assertIn("--coordinator-jobs-dir", completed.stdout)
        self.assertIn("deprecated", completed.stdout)

    def test_main_exits_with_error_when_cockpit_pane_is_missing(self) -> None:
        stderr = StringIO()
        with patch.object(TmuxClient, "list_panes", return_value=()), patch("sys.stderr", stderr):
            exit_code = cockpit_main.main(["--cockpit-pane", "%404"])

        self.assertEqual(exit_code, 1)
        self.assertIn("cockpit pane not found: %404", stderr.getvalue())

    def test_main_derives_cockpit_session_from_pane_record(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", session_name="main", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%9", session_name="work", title="pytest", command="python", width=80, height=20),
        )
        with (
            patch.object(TmuxClient, "list_panes", return_value=panes),
            patch.object(CockpitApp, "from_snapshot", return_value=DummyCockpitApp()) as from_snapshot,
        ):
            exit_code = cockpit_main.main(["--cockpit-pane", "%0"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(from_snapshot.call_args.kwargs["cockpit_session_name"], "main")
        self.assertEqual(from_snapshot.call_args.kwargs["jobs_by_pane"], {})

    def test_main_returns_zero_on_once_flag_without_starting_ui(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", session_name="main", title="ssh", command="bash", left=120, width=120, height=40),
        )
        with (
            patch.object(TmuxClient, "list_panes", return_value=panes),
            patch.object(CockpitApp, "from_snapshot") as from_snapshot,
        ):
            exit_code = cockpit_main.main(["--cockpit-pane", "%0", "--once"])

        self.assertEqual(exit_code, 0)
        from_snapshot.assert_not_called()


class Stage11StateTests(unittest.TestCase):
    def test_parse_list_panes_extracts_geometry(self) -> None:
        raw = "%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\n%4\tmain\t1\tssh\tbash\t120\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual(panes[0].pane_id, "%0")
        self.assertEqual(panes[0].session_name, "main")
        self.assertEqual(panes[0].window_index, "0")
        self.assertEqual(panes[1].left, 120)
        self.assertEqual(panes[1].width, 120)

    def test_slices_from_status_flattens_manager_sections(self) -> None:
        rows = slices_from_status(
            {
                "in_flight": [{"slice_id": "slice-run", "state": "running"}],
                "ready": ["slice-ready"],
                "held": [{"slice_id": "slice-held", "reasons": ["needs-review"]}],
                "attention": [{"slice_id": "slice-attn", "reason": "gate-failed"}],
                "recent_done": [{"slice_id": "slice-done", "gate_status": "passed"}],
            }
        )

        self.assertEqual(
            rows,
            (
                JobRow("slice-run", "running", "in_flight"),
                JobRow("slice-ready", "ready", "ready"),
                JobRow("slice-held", "blocked", "held", reason="needs-review"),
                JobRow("slice-attn", "attention", "attention", reason="gate-failed", needs_human=True),
                JobRow("slice-done", "passed", "recent_done"),
            ),
        )

    def test_slices_from_status_returns_empty_on_degraded_or_missing_keys(self) -> None:
        self.assertEqual(slices_from_status({"degraded": True, "degraded_reason": "manager-offline"}), ())
        self.assertEqual(slices_from_status({}), ())

    # --- #264：JOBS 要看得出「這是什麼 job」「為什麼卡住」「下一步做什麼」 ---

    def test_attention_row_carries_reason_actions_and_job_identity(self) -> None:
        """attention 條目本來就帶 reason/next_actions/builder_job_id，不可在攤平時丟掉。"""
        (row,) = slices_from_status(
            {
                "attention": [
                    {
                        "slice_id": "add-cortex-version-flag-build",
                        "job_state": "exited",
                        "reason": "candidate-worktree-dirty",
                        "next_actions": ["retry-build", "abandon", "retry-verify"],
                        "builder_job_id": "add-cortex-version-flag-build-56",
                        "target_branch": "feature/add-cortex-version-flag-build",
                    }
                ]
            }
        )

        self.assertEqual(row.state, "exited")
        self.assertEqual(row.reason, "candidate-worktree-dirty")
        self.assertEqual(row.next_actions, ("retry-build", "abandon", "retry-verify"))
        self.assertEqual(row.job_id, "add-cortex-version-flag-build-56")
        self.assertEqual(row.branch, "feature/add-cortex-version-flag-build")
        self.assertTrue(row.needs_human)
        # 卡在 attention = slice 還沒完成、被人工動作擋住。
        self.assertEqual(row.human_state, "阻塞中")
        self.assertIn("candidate-worktree-dirty", row.detail_line)
        self.assertIn(
            "cortex slice-action add-cortex-version-flag-build "
            "retry-build|abandon|retry-verify --actor $USER",
            row.detail_line,
        )

    def test_recent_done_needs_human_reads_as_awaiting_decision(self) -> None:
        """#264 回歸案例：`recent_done • needs_human` 是「跑完但 gate 沒過」，不是還在跑。"""
        (row,) = slices_from_status(
            {"recent_done": [{"slice_id": "wf-e13fa4daae-subagent-build", "gate_status": "needs_human"}]}
        )

        self.assertTrue(row.needs_human)
        self.assertEqual(row.human_state, "待裁決")
        # worktree/workflow 前綴降為次要，主顯示是看得懂的任務名。
        self.assertEqual(row.workflow_id, "wf-e13fa4daae")
        self.assertEqual(row.display_name, "subagent-build")

    def test_recent_done_row_uses_upstream_gate_reason_when_present(self) -> None:
        """manager handoff manifest 已有 gate_reason；上游一旦帶上來就要直接用。"""
        (row,) = slices_from_status(
            {
                "recent_done": [
                    {
                        "slice_id": "wf-e13fa4daae-subagent-build",
                        "gate_status": "needs_human",
                        "gate_reason": "pinned-input-mismatch",
                        "job_id": "wf-e13fa4daae-subagent-build-7",
                        "branch": "feature/wf-e13fa4daae",
                    }
                ]
            }
        )

        self.assertEqual(row.reason, "pinned-input-mismatch")
        self.assertEqual(row.job_id, "wf-e13fa4daae-subagent-build-7")
        self.assertEqual(row.branch, "feature/wf-e13fa4daae")
        self.assertIn("pinned-input-mismatch", row.detail_line)

    def test_needs_human_without_reason_says_so_instead_of_rendering_a_blank_row(self) -> None:
        """驗收條件：缺 reason／action 時要明說是上游沒給，不能產生無意義的狀態列。"""
        row = JobRow("wf-e13fa4daae-subagent-build", "needs_human", "recent_done", needs_human=True)

        self.assertEqual(row.detail_line, "上游未帶 reason／next_actions（manager status 契約缺口）")

    def test_needs_human_with_reason_but_no_actions_points_at_the_manifest(self) -> None:
        row = JobRow(
            "wf-e13fa4daae-subagent-build",
            "needs_human",
            "recent_done",
            reason="pinned-input-mismatch",
            needs_human=True,
        )

        self.assertIn("pinned-input-mismatch", row.detail_line)
        self.assertIn("無可執行 action", row.detail_line)

    def test_non_needs_human_row_has_no_detail_line(self) -> None:
        self.assertEqual(JobRow("slice-ready", "ready", "ready").detail_line, "")

    def test_held_row_carries_dependency_reasons_but_is_not_needs_human(self) -> None:
        """held 是依賴未滿足，會自己解開；不可混進「等人工」而稀釋真正要人看的列。"""
        (row,) = slices_from_status(
            {
                "held": [
                    {
                        "slice_id": "fix-dispatch-98-adversarial-review",
                        "reasons": ["dispatch-hold", "deps-unsatisfied:fix-dispatch-98-code-review"],
                    }
                ]
            }
        )

        self.assertEqual(row.state, "blocked")
        self.assertFalse(row.needs_human)
        self.assertEqual(row.human_state, "")
        self.assertEqual(row.detail_line, "")
        self.assertEqual(row.reason, "dispatch-hold; deps-unsatisfied:fix-dispatch-98-code-review")

    def test_group_job_rows_lifts_needs_human_above_routine_work(self) -> None:
        """現場 status 有 51 列、其中 11 列等人工；照 section 原序排，等人的全被
        ready／held 擠出畫面——面板高度有限，要人動手的必須排最前面。"""
        rows = (
            JobRow("ready-a", "ready", "ready"),
            JobRow("held-a", "blocked", "held"),
            JobRow("attn-a", "exited", "attention", needs_human=True),
            JobRow("run-a", "running", "in_flight"),
            JobRow("done-a", "needs_human", "recent_done", needs_human=True),
            JobRow("ready-b", "ready", "ready"),
        )

        ordered = [group.key for group in group_job_rows(rows)]

        self.assertEqual(ordered[:2], ["attn-a", "done-a"])
        self.assertEqual(ordered[2], "run-a")
        # 同群組內維持原本的 section 順序，畫面不會每次刷新就跳動。
        self.assertEqual(ordered[3:], ["ready-a", "held-a", "ready-b"])

    # --- #264：同一 workflow 的多個 phase 收成一群 ---

    def test_group_job_rows_folds_workflow_phases_into_one_group(self) -> None:
        """現場一個 workflow 常有 3~4 個 phase 同時 needs_human，各佔一列會把
        面板吃光：實測 51 列其實只有 22 群、11 筆 needs_human 只代表 6 件事。"""
        rows = slices_from_status(
            {
                "recent_done": [
                    {"slice_id": "wf-e13fa4daae-subagent-build", "gate_status": "needs_human"},
                    {"slice_id": "wf-e13fa4daae-code-review", "gate_status": "needs_human"},
                    {"slice_id": "wf-e13fa4daae-verification", "gate_status": "needs_human"},
                    {"slice_id": "wf-2fa3d22552-subagent-build", "gate_status": "needs_human"},
                ]
            }
        )

        groups = group_job_rows(rows)

        self.assertEqual([g.key for g in groups], ["wf-e13fa4daae", "wf-2fa3d22552"])
        big = groups[0]
        self.assertEqual(len(big.rows), 3)
        self.assertEqual(big.state_label, "3 phase 全待裁決")
        self.assertEqual(big.display_name, "wf-e13fa4daae")
        self.assertTrue(groups[1].is_single)
        self.assertEqual(groups[1].state_label, "needs_human")

    def test_group_job_rows_folds_plain_work_phases_by_known_suffix(self) -> None:
        """非 wf-* 的 work 也是同一組 phase（build / code-review / …），一樣要收攏。"""
        rows = slices_from_status(
            {
                "ready": ["fix-dispatch-98-build"],
                "held": [
                    {"slice_id": "fix-dispatch-98-code-review", "reasons": ["deps-unsatisfied"]},
                    {"slice_id": "fix-dispatch-98-verification", "reasons": ["deps-unsatisfied"]},
                ],
            }
        )

        (group,) = group_job_rows(rows)

        self.assertEqual(group.key, "fix-dispatch-98")
        self.assertEqual(len(group.rows), 3)
        # state 不一致（ready + blocked）時不謊稱單一狀態。
        self.assertEqual(group.state_label, "3 phase")

    def test_group_state_label_names_the_state_when_all_phases_agree(self) -> None:
        rows = slices_from_status(
            {
                "held": [
                    {"slice_id": "fix-dispatch-98-code-review", "reasons": ["x"]},
                    {"slice_id": "fix-dispatch-98-verification", "reasons": ["x"]},
                ]
            }
        )

        (group,) = group_job_rows(rows)

        self.assertEqual(group.state_label, "2 phase blocked")

    def test_group_keeps_unrecognised_slices_separate(self) -> None:
        """認不得的命名各自成群——寧可多幾列，也不要把不相干的東西併在一起。"""
        rows = (JobRow("alpha", "ready", "ready"), JobRow("beta", "ready", "ready"))

        self.assertEqual([g.key for g in group_job_rows(rows)], ["alpha", "beta"])

    def test_group_detail_line_is_reserved_for_work_that_needs_a_human(self) -> None:
        """held 的 reasons 攤開實測可長到 500+ 字，會把真正等人的群擠掉；
        第二行只留給要人動手的。"""
        rows = slices_from_status(
            {
                "held": [
                    {
                        "slice_id": "fix-dispatch-98-code-review",
                        "reasons": ["dispatch-hold", "deps-unsatisfied:fix-dispatch-98-build"],
                    },
                    {"slice_id": "fix-dispatch-98-verification", "reasons": ["dispatch-hold"]},
                ]
            }
        )

        (group,) = group_job_rows(rows)

        self.assertFalse(group.needs_human)
        self.assertEqual(group.detail_line, "")
        self.assertEqual(group.note, "")

    def test_group_detail_line_shares_a_common_reason_and_shortens_phase_names(self) -> None:
        rows = slices_from_status(
            {
                "attention": [
                    {"slice_id": "fix-dispatch-98-code-review", "reason": "candidate-dirty"},
                    {"slice_id": "fix-dispatch-98-verification", "reason": "candidate-dirty"},
                ]
            }
        )

        (group,) = group_job_rows(rows)

        # 共用前綴剝掉，只留辨識用的 phase 尾段。
        self.assertEqual(group.detail_line, "candidate-dirty · code-review / verification")

    def test_group_detail_line_lists_per_phase_when_reasons_differ(self) -> None:
        rows = slices_from_status(
            {
                "attention": [
                    {"slice_id": "fix-dispatch-98-code-review", "reason": "candidate-dirty"},
                    {"slice_id": "fix-dispatch-98-verification", "reason": "pinned-input-mismatch"},
                ]
            }
        )

        (group,) = group_job_rows(rows)

        self.assertEqual(
            group.detail_line,
            "code-review: candidate-dirty / verification: pinned-input-mismatch",
        )

    def test_group_note_flags_missing_reason_without_spending_a_line(self) -> None:
        """缺 reason 仍要講，但不值得佔第二行——那一行要留給真的有下一步可做的群。"""
        rows = slices_from_status(
            {
                "recent_done": [
                    {"slice_id": "wf-e13fa4daae-subagent-build", "gate_status": "needs_human"},
                    {"slice_id": "wf-e13fa4daae-code-review", "gate_status": "needs_human"},
                ]
            }
        )

        (group,) = group_job_rows(rows)

        self.assertEqual(group.note, "原因未知")
        self.assertEqual(group.detail_line, "")

    def test_rows_carry_project_attribution_when_upstream_provides_it(self) -> None:
        """manager 是跨 repo 派工的：現場 JOBS 上 10 筆 needs_human 全屬 paulsha-cortex，
        paulshaclaw 一筆都沒有。不標 project，operator 不知道該去哪個 repo 動手。"""
        rows = slices_from_status(
            {
                "attention": [
                    {"slice_id": "attn-a", "repo": "hamanpaul/paulsha-cortex", "reason": "x"}
                ],
                "recent_done": [
                    {
                        "slice_id": "wf-e13fa4daae-subagent-build",
                        "gate_status": "needs_human",
                        "workflow_repo": "hamanpaul/paulsha-cortex",
                    }
                ],
                "in_flight": [{"slice_id": "run-a", "repo": "hamanpaul/paulshaclaw"}],
            }
        )

        by_id = {row.slice_id: row for row in rows}
        self.assertEqual(by_id["attn-a"].repo, "hamanpaul/paulsha-cortex")
        self.assertEqual(by_id["attn-a"].project, "paulsha-cortex")
        # recent_done 走 workflow_repo 別名，同樣要認得。
        self.assertEqual(by_id["wf-e13fa4daae-subagent-build"].project, "paulsha-cortex")
        self.assertEqual(by_id["run-a"].project, "paulshaclaw")

    def test_project_is_empty_when_upstream_omits_repo(self) -> None:
        """上游還沒送 repo 前不可亂猜歸屬——寧可不顯示，也不能標錯 project。"""
        (row,) = slices_from_status({"recent_done": [{"slice_id": "wf-x-build"}]})

        self.assertEqual(row.repo, "")
        self.assertEqual(row.project, "")

    def test_display_name_keeps_plain_slice_ids_intact(self) -> None:
        row = JobRow("add-cortex-version-flag-build", "exited", "attention")

        self.assertEqual(row.workflow_id, "")
        self.assertEqual(row.display_name, "add-cortex-version-flag-build")

    def test_parse_list_panes_skips_malformed_numeric_fields(self) -> None:
        raw = "%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\n%4\tmain\t1\tssh\tbash\tnan\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual([pane.pane_id for pane in panes], ["%0"])

    def test_parse_list_panes_extracts_session_window(self) -> None:
        raw = (
            "%1\tmain\t0\tserver\tbash\t0\t0\t100\t40\t1\n"
            "%9\twork\t2\tpytest\tpython\t100\t0\t100\t40\t0\n"
        )
        panes = parse_list_panes(raw)

        self.assertEqual([(pane.pane_id, pane.session_name, pane.window_index) for pane in panes], [
            ("%1", "main", "0"),
            ("%9", "work", "2"),
        ])
        self.assertTrue(panes[0].active)
        self.assertFalse(panes[1].active)

    def test_parse_list_panes_reads_current_path_and_host_short(self) -> None:
        raw = "%0\tmain\t0\t9900X\tbash\t0\t0\t120\t40\t1\t/dev/pts/7\t/opt/paul/prj/cockpit\t9900X\n"
        panes = parse_list_panes(raw)

        self.assertEqual(panes[0].pane_tty, "/dev/pts/7")
        self.assertEqual(panes[0].pane_current_path, "/opt/paul/prj/cockpit")
        self.assertEqual(panes[0].host_short, "9900X")

    def test_pane_display_label_includes_session_window(self) -> None:
        pane = pane_record("%12", session_name="work", window_index="2", title="pytest")

        self.assertEqual(pane_display_label(pane), "work:2 %12 pytest")

    def test_pane_display_label_falls_back_to_derived_summary(self) -> None:
        pane = PaneRecord(
            pane_id="%0", session_name="main", window_index="0", title="", command="minicom",
            left=0, top=0, width=80, height=24, active=False,
            pane_tty="/dev/pts/2", summary="minicom COM0",
        )

        self.assertEqual(pane_display_label(pane), "main:0 %0 minicom COM0")

    def test_derive_summary_minicom_reads_com_from_process(self) -> None:
        pane = pane_record("%0", title="", command="minicom")
        pane = PaneRecord(**{**pane.__dict__, "pane_tty": "/dev/pts/2"})
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="  minicom -D /dev/pts/17 --color=on -C /opt/x/b-log/mini_COM0_260610.log\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "minicom COM0")

    def test_derive_summary_non_minicom_empty_title_uses_command(self) -> None:
        pane = pane_record("%9", title="", command="node")
        self.assertEqual(derive_summary(pane), "[node]")

    def test_derive_summary_hostname_title_falls_back_to_cwd_name(self) -> None:
        panes = (
            pane_record(
                "%9",
                title="9900X",
                command="bash",
                pane_current_path="/opt/paul/prj/repo-a",
                host_short="9900X",
            ),
            pane_record(
                "%10",
                title="9900X",
                command="bash",
                pane_current_path="/opt/paul/prj/repo-b",
                host_short="9900X",
            ),
        )
        self.assertEqual([derive_summary(pane) for pane in panes], ["repo-a", "repo-b"])

    def test_derive_summary_wrapped_minicom_reads_com_from_tty(self) -> None:
        # serialwrap-minicom wrapper 底下：tmux 回報 command=bash，但 tty 上跑著 minicom。
        pane = pane_record(
            "%3",
            title="",
            command="bash",
            pane_tty="/dev/pts/9",
            pane_current_path="/opt/paul_chen",
            host_short="9900X",
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=(
                "  bash /opt/paul_chen/.local/bin/serialwrap-minicom COM0\n"
                "  /usr/bin/minicom -D /dev/pts/8 --color=on -C /opt/paul_chen/b-log/mini_COM0_x.log\n"
            ),
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "minicom COM0")

    def test_derive_summary_shell_pane_without_minicom_falls_back_to_cwd(self) -> None:
        # 一般 idle bash pane：tty 上沒有 minicom，須退回 cwd basename、不誤標 minicom。
        pane = pane_record(
            "%1",
            title="",
            command="bash",
            pane_tty="/dev/pts/3",
            pane_current_path="/opt/paul/prj/repo-a",
            host_short="9900X",
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="  -bash\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "repo-a")

    def test_derive_summary_shell_pane_empty_tty_spawns_no_ps(self) -> None:
        # 成本邊界：無 tty 的 shell pane 不得觸發 ps（_minicom_summary 對空 tty 立即回 None）。
        pane = pane_record(
            "%7",
            title="9900X",
            command="bash",
            pane_tty="",
            pane_current_path="/opt/paul/prj/repo-a",
            host_short="9900X",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run") as run:
            self.assertEqual(derive_summary(pane), "repo-a")
            run.assert_not_called()

    def test_derive_summary_benign_minicom_substring_not_mislabeled(self) -> None:
        # `man minicom` / `vim serialwrap-minicom` 含 "minicom" 子字串但 argv0 非
        # minicom binary，不得被誤標成 minicom（對抗審查 Imp-2）。
        pane = pane_record(
            "%8",
            title="",
            command="bash",
            pane_tty="/dev/pts/5",
            pane_current_path="/opt/paul/prj/repo-b",
            host_short="9900X",
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="  man minicom\n  vim /opt/x/.local/bin/serialwrap-minicom\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "repo-b")

    def test_derive_summary_uses_minicom_map_without_probing(self) -> None:
        # 給定 batch map 時，derive_summary 只查表、不得再 fork ps（對抗審查 Imp-3）。
        pane = pane_record(
            "%3",
            title="",
            command="bash",
            pane_tty="/dev/pts/9",
            pane_current_path="/opt/paul_chen",
            host_short="9900X",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run") as run:
            self.assertEqual(
                derive_summary(pane, {"pts/9": "minicom COM0"}), "minicom COM0"
            )
            run.assert_not_called()

    def test_minicom_map_builds_tty_to_label_and_skips_benign(self) -> None:
        # 單次 ps -e 掃描 → {tty: minicom COMx}；no-tty(?)、非 minicom binary 皆排除。
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=(
                "pts/9 /usr/bin/minicom -D /dev/pts/8 -C /opt/x/b-log/mini_COM0_x.log\n"
                "pts/3 -bash\n"
                "?     /usr/lib/systemd/systemd\n"
                "pts/5 man minicom\n"
            ),
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(_minicom_map(), {"pts/9": "minicom COM0"})

    def test_minicom_summary_returns_none_on_ps_timeout(self) -> None:
        # ps 逾時（TimeoutExpired ⊂ SubprocessError）須 fail-soft 回 None（Min-5）。
        with patch(
            "paulshaclaw.cockpit.tmux.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ps", timeout=1),
        ):
            self.assertIsNone(_minicom_summary("/dev/pts/9"))

    def test_derive_summary_root_path_falls_back_to_slash(self) -> None:
        pane = pane_record("%9", title="9900X", command="bash", pane_current_path="/", host_short="9900X")
        self.assertEqual(derive_summary(pane), "/")

    def test_derive_summary_prefers_pane_title(self) -> None:
        pane = pane_record("%3", title="Debug thing", command="claude")
        self.assertEqual(derive_summary(pane), "Debug thing")

    def test_parse_list_panes_reads_pane_tty(self) -> None:
        raw = "%0\tmain\t0\t\tminicom\t0\t0\t120\t40\t1\t/dev/pts/7\n"
        panes = parse_list_panes(raw)
        self.assertEqual(panes[0].pane_tty, "/dev/pts/7")
        self.assertEqual(panes[0].command, "minicom")

    def test_on_mount_schedules_pane_and_sysmon_ticks(self) -> None:
        # 兩段式節奏（htop 風）：慢 tick 重載 tmux panes、快 tick 只刷 /proc 系統監控。
        app = self._minimal_app()
        with patch.object(app, "_refresh_widgets"), patch.object(app, "set_interval") as set_interval:
            app.on_mount()
        scheduled = {call.args[1]: call.args[0] for call in set_interval.call_args_list}
        self.assertEqual(scheduled.get(app._on_refresh_tick), REFRESH_INTERVAL_SECONDS)
        self.assertEqual(scheduled.get(app._on_sysmon_tick), SYSMON_INTERVAL_SECONDS)
        # sysmon tick 必須比 pane 重載快，才是「即時」監控
        self.assertLess(SYSMON_INTERVAL_SECONDS, REFRESH_INTERVAL_SECONDS)

    def test_sysmon_tick_updates_banner_without_reloading_panes(self) -> None:
        # 高頻 tick 只讀 /proc 就地更新 banner，不得 fork tmux（不吃資源的關鍵）。
        reloads = {"n": 0}

        def loader(**kwargs):
            reloads["n"] += 1
            return self._minimal_panes()

        app = self._minimal_app(pane_loader=loader)
        with patch.object(app, "_refresh_banner") as refresh_banner:
            app._on_sysmon_tick()
        refresh_banner.assert_called_once()
        self.assertEqual(reloads["n"], 0)

    def test_refresh_skips_work_list_rebuild_when_content_unchanged(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", title="active", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", session_name="main", title="a1", command="node", left=0, top=40, width=80, height=20),
            pane_record("%2", session_name="main", title="a2", command="node", left=80, top=40, width=80, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes, cockpit_pane_id="%0", cockpit_session_name="main",
            jobs_by_pane={}, actions=LayoutActionService(),
        )
        widgets = {key: Mock() for key in ("#work-list", "#global-jobs")}

        with patch.object(app, "query_one", side_effect=lambda sel, *a, **k: widgets[sel]):
            app._refresh_widgets()
            app._refresh_widgets()  # identical content -> list not rebuilt again
            self.assertEqual(widgets["#work-list"].clear.call_count, 1)
            # JOBS 每個 tick 都經 set_groups 或 set_message 之一餵資料（見 jobs_panel 契約），
            # 不再是直接 update() 一個 renderable。
            jobs_refresh_calls = (
                widgets["#global-jobs"].set_groups.call_count
                + widgets["#global-jobs"].set_message.call_count
            )
            self.assertGreaterEqual(jobs_refresh_calls, 2)

            app.state = app.state.move_selection(1)  # cursor moves to a different candidate
            app._refresh_widgets()
            self.assertEqual(widgets["#work-list"].clear.call_count, 2)

    def test_refresh_reloads_panes_with_single_loader_call(self) -> None:
        seen: dict[str, object] = {}

        def loader(*, cockpit_pane_id: str):
            seen["cockpit_pane_id"] = cockpit_pane_id
            return self._minimal_panes()

        app = self._minimal_app(pane_loader=loader)
        with patch.object(app, "_refresh_widgets"):
            app._reconcile_state()
        self.assertEqual(seen["cockpit_pane_id"], "%0")

    def _minimal_panes(self) -> tuple[PaneRecord, ...]:
        return (
            pane_record("%0", session_name="main", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", title="ssh", command="bash", left=120, top=0, width=120, height=40),
        )

    def _minimal_app(self, *, pane_loader=None) -> CockpitApp:
        return CockpitApp.from_snapshot(
            panes=self._minimal_panes(),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=LayoutActionService(),
            pane_loader=pane_loader,
        )

    def _install_mutable_screen(self, app, initial=None) -> dict:
        """Give ``app`` a controllable ``screen`` for screen-aware actions.

        textual's ``App.screen`` is a read-only property, so tests cannot assign
        it directly; patch it with a holder-backed PropertyMock and return the
        holder so tests can seed/read the "current screen" and have a mocked
        ``push_screen`` update it.
        """
        holder = {"screen": initial}
        patcher = patch.object(
            type(app), "screen", create=True, new_callable=PropertyMock, side_effect=lambda: holder["screen"]
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return holder

    def test_list_panes_uses_dash_a_flag(self) -> None:
        client = TmuxClient()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\t1\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed) as run_mock:
            panes = client.list_panes(cockpit_pane_id="%0")

        # list_panes now also runs a single `ps -e` scan (minicom map); the tmux
        # list-panes call is the first subprocess, so assert against that one.
        command = run_mock.call_args_list[0].args[0]
        self.assertEqual(command[:3], ["tmux", "list-panes", "-a"])
        self.assertNotIn("-t", command)
        self.assertIn("#{session_name}", command[-1])
        self.assertIn("#{window_index}", command[-1])
        self.assertIn("#{pane_current_path}", command[-1])
        self.assertIn("#{host_short}", command[-1])
        self.assertEqual(panes[0].session_name, "main")

    def test_tmux_client_returns_empty_when_tmux_list_panes_fails(self) -> None:
        client = TmuxClient()
        with patch(
            "paulshaclaw.cockpit.tmux.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["tmux", "list-panes", "-a"]),
        ):
            panes = client.list_panes(cockpit_pane_id="%0")

        self.assertEqual(panes, ())

    def test_choose_startup_slot_excludes_cockpit_even_when_same_size(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
        )

        anchor = choose_startup_slot(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual(anchor, SlotAnchor(left=120, top=0, width=120, height=40))

    def test_choose_startup_slot_only_considers_cockpit_session(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="huge", left=0, top=0, width=300, height=80),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
        )

        anchor = choose_startup_slot(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual(anchor, SlotAnchor(left=120, top=0, width=120, height=40))

    def test_active_slot_scoped_to_cockpit_window(self) -> None:
        # 根因修復：active slot 只在 cockpit 所在 window 內取；別的 window 就算有更大 pane 也不算 active
        # （否則 swap 會把可見 pane 換去看不到的 window，看似「沒作用」）。跨 window 仍可當候選。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%1", session_name="main", window_index="0", title="win0-slot", left=0, top=25, width=100, height=24),
            pane_record("%9", session_name="main", window_index="1", title="win1-bigger", left=0, top=0, width=200, height=60),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.active_section], ["%1"])
        self.assertEqual(state.active_pane.pane_id, "%1")
        # 同 session 的別 window pane 仍是候選（收斂只排除「他 session」，不排除「他 window」）。
        self.assertIn("%9", [pane.pane_id for pane in state.candidate_section])

    def test_choose_startup_slot_none_when_cockpit_alone_in_its_window(self) -> None:
        # cockpit 獨佔自己的 window（其他 pane 在別 window）→ 無 active slot，回 None（不 raise、不 crash）。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", width=100, height=40),
            pane_record("%9", session_name="main", window_index="1", title="elsewhere", width=100, height=40),
        )
        self.assertIsNone(
            choose_startup_slot(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertIsNone(state.active_pane)
        # 同 session 的別 window pane 仍是候選（cockpit 獨佔自己 window → 無 active，但候選不空）。
        self.assertIn("%9", [pane.pane_id for pane in state.candidate_section])

    def test_refresh_recovers_active_when_slot_pane_resized(self) -> None:
        # 硬化（finding 1）：slot pane 被 resize 使 geometry 不再吻合啟動 anchor → refresh 重新推導 →
        # active 自癒，不會永久卡在 active-slot-lost。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%1", session_name="main", window_index="0", title="slot", left=0, top=25, width=100, height=24),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertEqual(state.active_pane.pane_id, "%1")

        resized = state.refresh((
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%1", session_name="main", window_index="0", title="slot", left=0, top=25, width=100, height=30),
        ))
        self.assertEqual(resized.active_pane.pane_id, "%1")
        self.assertIsNone(resized.degraded_reason)

    def test_refresh_rederives_cockpit_window_after_renumber(self) -> None:
        # 硬化（finding 2）：window 被 renumber（0→3）→ refresh 重新推導 cockpit window → active 仍找得到。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%1", session_name="main", window_index="0", title="slot", left=0, top=25, width=100, height=24),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertEqual(state.cockpit_window_index, "0")

        renumbered = state.refresh((
            pane_record("%0", session_name="main", window_index="3", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%1", session_name="main", window_index="3", title="slot", left=0, top=25, width=100, height=24),
        ))
        self.assertEqual(renumbered.cockpit_window_index, "3")
        self.assertEqual(renumbered.active_pane.pane_id, "%1")
        self.assertIsNone(renumbered.degraded_reason)

    def test_refresh_acquires_slot_after_pane_added_to_lone_cockpit_window(self) -> None:
        # 硬化（finding 3）：開機時 cockpit 獨佔 window（slot None）→ 之後 split 出新 pane → refresh 取得 slot。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", width=100, height=40),
            pane_record("%9", session_name="main", window_index="1", title="elsewhere", width=100, height=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertIsNone(state.active_pane)

        grown = state.refresh((
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=20),
            pane_record("%5", session_name="main", window_index="0", title="new", left=0, top=21, width=100, height=19),
            pane_record("%9", session_name="main", window_index="1", title="elsewhere", width=100, height=40),
        ))
        self.assertEqual(grown.active_pane.pane_id, "%5")
        self.assertIsNone(grown.degraded_reason)

    def test_lone_cockpit_window_reports_no_active_slot_not_lost(self) -> None:
        # Copilot review PR #173：cockpit 獨佔自身 window（slot 本就 None）是正常「無落點」，
        # 不該誤標成 active-slot-lost（那是「原本有、後來不見」才對）。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", width=100, height=40),
            pane_record("%9", session_name="main", window_index="1", title="elsewhere", width=100, height=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertEqual(state.degraded_reason, "no-active-slot")

        still_alone = state.refresh(panes)
        self.assertIsNone(still_alone.active_pane)
        self.assertEqual(still_alone.degraded_reason, "no-active-slot")

    def test_refresh_promotes_cross_window_pane_swapped_into_slot(self) -> None:
        # 跨 window swap 後：被選的 %9 移進 cockpit window 的 slot geom → reconcile 後成為 active。
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%1", session_name="main", window_index="0", title="slot", left=0, top=25, width=100, height=24),
            pane_record("%9", session_name="main", window_index="1", title="other", left=0, top=0, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertEqual(state.active_pane.pane_id, "%1")

        swapped = state.refresh((
            pane_record("%0", session_name="main", window_index="0", title="cockpit", left=0, top=0, width=100, height=24),
            pane_record("%9", session_name="main", window_index="0", title="other", left=0, top=25, width=100, height=24),
            pane_record("%1", session_name="main", window_index="1", title="slot", left=0, top=0, width=80, height=20),
        ))
        self.assertEqual(swapped.active_pane.pane_id, "%9")
        self.assertIsNone(swapped.degraded_reason)

    def test_state_segments_active_and_candidate_sections(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.active_section], ["%4"])
        self.assertEqual([pane.pane_id for pane in state.candidate_section], ["%1", "%2"])

    def test_active_section_excludes_other_sessions_with_same_anchor(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", title="active", left=120, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="collision", left=120, top=0, width=120, height=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.active_section], ["%4"])
        self.assertNotIn("%9", [pane.pane_id for pane in state.candidate_section])

    def test_candidate_section_only_lists_cockpit_session_and_prioritizes_cockpit_window(self) -> None:
        panes = (
            pane_record("%0", session_name="main", window_index="0", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", window_index="0", left=120, top=0, width=120, height=40),
            pane_record("%1", session_name="main", window_index="0", left=0, top=40, width=80, height=20),
            pane_record("%6", session_name="main", window_index="2", left=0, top=0, width=80, height=20),
            pane_record("%5", session_name="main", window_index="1", left=0, top=0, width=80, height=20),
            pane_record("%7", session_name="beta", window_index="2", left=0, top=0, width=80, height=20),
            pane_record("%3", session_name="alpha", window_index="1", left=0, top=0, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.candidate_section], ["%1", "%5", "%6"])

    def test_candidate_section_sorts_window_index_numerically(self) -> None:
        panes = (
            pane_record("%0", session_name="main", window_index="0", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", window_index="0", left=120, top=0, width=120, height=40),
            pane_record("%10", session_name="main", window_index="10", left=0, top=0, width=80, height=20),
            pane_record("%2", session_name="main", window_index="2", left=0, top=0, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        ids = [pane.pane_id for pane in state.candidate_section]
        self.assertLess(ids.index("%2"), ids.index("%10"))

    def test_refresh_active_lost_only_when_cockpit_session_pane_gone(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", title="active", left=120, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="remote", left=120, top=0, width=120, height=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        stable = state.refresh((
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", title="active", left=120, top=0, width=120, height=40),
        ))
        self.assertIsNone(stable.degraded_reason)

        lost = state.refresh((
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="collision", left=120, top=0, width=120, height=40),
        ))
        self.assertEqual(lost.degraded_reason, "active-slot-lost")
        self.assertEqual(lost.active_section, ())

    def test_refresh_preserves_selected_pane_when_candidate_order_changes(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", title="active", left=120, top=0, width=120, height=40),
            pane_record("%1", session_name="main", window_index="1", title="agent1", top=40, width=80, height=20),
            pane_record("%2", session_name="main", window_index="2", title="agent2", left=80, top=40, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        state = state.move_selection(1)

        refreshed = state.refresh((
            pane_record("%0", session_name="main", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", title="active", left=120, top=0, width=120, height=40),
            pane_record("%2", session_name="main", window_index="0", title="agent2", left=80, top=40, width=80, height=20),
            pane_record("%1", session_name="main", window_index="3", title="agent1", top=40, width=80, height=20),
        ))

        self.assertEqual(refreshed.selected_pane.pane_id, "%2")

    def test_format_work_pane_subtitle_includes_cockpit_session_window(self) -> None:
        panes = (
            pane_record("%0", session_name="main", window_index="0", title="cockpit", width=120, height=40),
            pane_record("%4", session_name="main", window_index="0", title="active", left=120, width=120, height=40),
            pane_record("%1", session_name="main", window_index="1", title="agent1", top=40, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual(format_work_pane_subtitle(state), "main:0 · 1 panes")

    def test_help_modal_lists_all_bindings(self) -> None:
        """up/down/enter 不再是 App 層 BINDINGS（WORK／JOBS 各自的 focused widget 原生
        處理，見 #264 Tree 化），help 改講 tab 切換 focus 與兩個面板各自的鍵位。"""
        help_text = HelpModal.render_help_text(CockpitApp.BINDINGS)

        self.assertIn("tab: 切換面板", help_text)
        self.assertIn("c: 回 cockpit", help_text)
        self.assertIn("m: manager", help_text)
        self.assertIn("q: 離開", help_text)
        self.assertIn("t: tick", help_text)
        self.assertIn("j: JOBS 收合", help_text)
        self.assertIn("question_mark: 說明", help_text)
        # tab 切換 focus，WORK／JOBS 各自的上下鍵/enter 語意要交代清楚。
        self.assertIn("tab 切換 WORK／JOBS focus", help_text)
        self.assertIn("WORK：↑↓ 選 pane，enter 或雙擊把選中的 pane 換到我面前", help_text)
        self.assertIn("JOBS：↑↓ 移動節點，enter/space 展開或收合該群", help_text)
        self.assertIn("JOBS 是可捲動的樹", help_text)

    def test_cockpit_app_imports_manager_client_without_coordinator_dependency(self) -> None:
        tree = ast.parse(inspect.getsource(sys.modules["paulshaclaw.cockpit.app"]))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")

        legacy_prefix = ".".join(("paulshaclaw", "coordinator"))
        self.assertFalse(any(name.startswith(legacy_prefix) for name in imported))

    def test_action_manager_panel_pushes_manager_modal_from_status(self) -> None:
        app = self._minimal_app()
        self._install_mutable_screen(app, None)
        pushed: list[object] = []
        app.push_screen = pushed.append
        app.manager_client = SimpleNamespace(
            read_status=lambda: {
                "updated_at": "2026-07-03T12:00:00+00:00",
                "daemon": {"pid": 1234, "last_tick_at": "2026-07-03T11:59:00+00:00", "idle": False},
                "ready": ["slice-a"],
                "in_flight": [{"slice_id": "slice-b", "state": "running"}],
                "recent_done": [{"slice_id": "slice-c", "gate_status": "passed"}],
                "degraded": False,
                "degraded_reason": None,
            }
        )

        app.action_manager_panel()

        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], ManagerModal)
        self.assertIn("slice-a", pushed[0].status_text)

    def test_action_manager_tick_starts_background_submit_before_refresh(self) -> None:
        app = self._minimal_app()
        self._install_mutable_screen(app, None)
        fake_client = SimpleNamespace(
            submit_calls=[],
            submit_request=lambda req_type, args, requested_by: fake_client.submit_calls.append((req_type, args, requested_by)) or "req-1",
        )
        started: list[dict[str, object]] = []

        class FakeThread:
            def __init__(self, *, target, daemon):
                started.append({"target": target, "daemon": daemon, "started": False})

            def start(self):
                started[-1]["started"] = True

        app.manager_client = fake_client
        app.thread_factory = FakeThread
        app.call_from_thread = lambda callback: callback()
        app._after_manager_tick = Mock()

        app.action_manager_tick()

        self.assertEqual(fake_client.submit_calls, [])
        self.assertEqual(len(started), 1)
        self.assertTrue(started[0]["daemon"])
        self.assertTrue(started[0]["started"])

        started[0]["target"]()

        self.assertEqual(fake_client.submit_calls, [("tick", {}, "cockpit")])
        app._after_manager_tick.assert_called_once_with(None)

    def test_action_manager_tick_surfaces_submit_error_and_refreshes(self) -> None:
        app = self._minimal_app()
        self._install_mutable_screen(app, None)
        started: list[dict[str, object]] = []

        class FakeThread:
            def __init__(self, *, target, daemon):
                started.append({"target": target, "daemon": daemon, "started": False})

            def start(self):
                started[-1]["started"] = True

        def fail_submit(req_type, args, requested_by):
            raise PermissionError("control root denied")

        app.manager_client = SimpleNamespace(submit_request=fail_submit)
        app.thread_factory = FakeThread
        app.call_from_thread = lambda callback: callback()
        app.notify = Mock()
        with patch.object(app, "_refresh_manager_panel") as refresh, patch.object(app, "_reconcile_state") as reconcile:
            app.action_manager_tick()
            started[0]["target"]()

        app.notify.assert_called_once()
        self.assertIn("PermissionError: control root denied", app.notify.call_args.args[0])
        refresh.assert_called_once_with()
        reconcile.assert_called_once_with()

    def test_refresh_tick_updates_manager_panel_when_open(self) -> None:
        app = self._minimal_app()
        with (
            patch.object(app, "_reconcile_state") as reconcile,
            patch.object(app, "_refresh_jobs_panel") as refresh_jobs,
            patch.object(app, "_refresh_manager_panel") as refresh,
        ):
            app._on_refresh_tick()

        reconcile.assert_called_once_with()
        refresh_jobs.assert_called_once_with()
        refresh.assert_called_once_with()

    def test_refresh_widgets_renders_manager_slices_in_jobs_panel(self) -> None:
        app = self._minimal_app()
        widgets = {key: Mock() for key in ("#work-list", "#global-jobs")}
        status = {
            "in_flight": [{"slice_id": "slice-run", "state": "running"}],
            "ready": ["slice-ready"],
            "held": [{"slice_id": "slice-held"}],
            "attention": [{"slice_id": "slice-attn"}],
            "recent_done": [{"slice_id": "slice-done", "gate_status": "passed"}],
            "degraded": False,
            "degraded_reason": None,
        }
        app.manager_client = SimpleNamespace(read_status=lambda: status)

        with patch.object(app, "query_one", side_effect=lambda sel, *a, **k: widgets[sel]):
            app._refresh_widgets()

        self.assertEqual(widgets["#global-jobs"].border_title, "JOBS")
        # slice-attn 落在 attention（= needs_human），border 直接把「幾件等人」講出來。
        self.assertEqual(widgets["#global-jobs"].border_subtitle, "5 slices · 1 待人工")
        # 有 rows 時 app 把分好群的 JobGroup 直接餵給 widget（渲染成 node 是 widget 自己的事）。
        (groups,), _ = widgets["#global-jobs"].set_groups.call_args
        self.assertEqual(groups, group_job_rows(slices_from_status(status)))
        rendered = _flatten_nodes(build_jobs_nodes(groups))
        self.assertIn("slice-run", rendered)
        self.assertIn("slice-done", rendered)

    def test_build_jobs_nodes_carries_needs_human_reason_and_next_step(self) -> None:
        """#264：operator 不看原始 log 就要知道為什麼卡住、下一步敲什麼。"""
        status = {
            "attention": [
                {
                    "slice_id": "add-cortex-version-flag-build",
                    "job_state": "exited",
                    "reason": "candidate-worktree-dirty",
                    "next_actions": ["retry-build", "abandon"],
                    "builder_job_id": "add-cortex-version-flag-build-56",
                }
            ],
            "recent_done": [
                {
                    "slice_id": "wf-e13fa4daae-subagent-build",
                    "gate_status": "needs_human",
                    "workflow_repo": "hamanpaul/paulsha-cortex",
                }
            ],
            "degraded": False,
        }
        groups = group_job_rows(slices_from_status(status))
        rendered = _flatten_nodes(build_jobs_nodes(groups))

        self.assertIn("candidate-worktree-dirty", rendered)
        self.assertIn(
            "cortex slice-action add-cortex-version-flag-build retry-build|abandon --actor $USER",
            rendered,
        )
        # 兩種 needs_human 語意在畫面上分得開。
        self.assertIn("阻塞中", rendered)
        self.assertIn("待裁決", rendered)
        # workflow hash 退成次要，主欄位是看得懂的任務名。
        self.assertIn("subagent-build", rendered)
        self.assertIn("wf-e13fa4daae", rendered)
        # 上游有給 repo 時，project 要出現在次要欄的最前面。
        self.assertIn("paulsha-cortex", rendered)
        # 上游沒帶 reason 時明說，而不是留一列空白狀態。
        self.assertIn("原因未知", rendered)
        # needs_human 群必須排最前面、預設展開，operator 一進面板就看得到。
        # （group key 會剝掉已知 phase 後綴 `-build`，見 _group_key；display_name
        # 保留完整 slice_id，上面的 rendered 斷言已經驗過看得懂的名字還在。）
        self.assertEqual(groups[0].key, "add-cortex-version-flag")
        nodes = build_jobs_nodes(groups)
        self.assertEqual(nodes[0].key, "add-cortex-version-flag")
        self.assertTrue(nodes[0].expand)

    def test_build_jobs_nodes_keeps_needs_human_group_first_when_routine_rows_are_plentiful(
        self,
    ) -> None:
        """回歸現場情況：ready 多到面板單頁裝不下時，等人工的群仍要排最前面、
        整棵樹裡一個都不會不見——捲動取代了先前的行預算截斷。"""
        status = {
            "ready": [f"routine-slice-{index}" for index in range(20)],
            "attention": [
                {
                    "slice_id": "add-cortex-version-flag-build",
                    "job_state": "exited",
                    "reason": "candidate-worktree-dirty",
                    "next_actions": ["retry-build"],
                }
            ],
            "degraded": False,
        }
        groups = group_job_rows(slices_from_status(status))
        nodes = build_jobs_nodes(groups)

        self.assertEqual(len(nodes), len(groups))
        self.assertEqual(nodes[0].key, "add-cortex-version-flag")
        self.assertTrue(nodes[0].expand)
        rendered = _flatten_nodes(nodes)
        self.assertIn("candidate-worktree-dirty", rendered)

    # --- #264：CJK 顯示寬度與面板可用寬度 ---

    def test_display_width_counts_cjk_as_two_columns(self) -> None:
        """`4 phase 全待裁決` len() 是 12 但終端佔 16 欄；用 len() 排版整欄會歪。"""
        self.assertEqual(_display_width("needs_human"), 11)
        self.assertEqual(_display_width("4 phase 全待裁決"), 16)
        self.assertEqual(_display_width("待裁決"), 6)

    def test_pad_display_aligns_mixed_width_columns(self) -> None:
        padded_ascii = _pad_display("exited", 16)
        padded_cjk = _pad_display("4 phase 全待裁決", 16)

        self.assertEqual(_display_width(padded_ascii), 16)
        self.assertEqual(_display_width(padded_cjk), 16)

    def test_ellipsize_middle_measures_by_display_width(self) -> None:
        result = _ellipsize_middle("待裁決待裁決待裁決", 10)

        self.assertLessEqual(_display_width(result), 10)
        self.assertIn("…", result)

    def test_fit_trailer_drops_whole_items_from_the_tail(self) -> None:
        """硬切字元會把 `paulsha-cortex` 砍成半個名字，比少顯示一項更難讀。"""
        fitted = _fit_trailer(("paulsha-cortex", "wf-e13fa4daae", "原因未知", "job-99"), 32)

        self.assertIn("paulsha-cortex", fitted)
        self.assertNotIn("job-99", fitted)
        self.assertTrue(fitted.endswith("…"))
        self.assertLessEqual(_display_width(fitted), 32)

    def test_fit_trailer_keeps_everything_when_it_fits(self) -> None:
        fitted = _fit_trailer(("paulsha-cortex", "待裁決"), 40)

        self.assertEqual(fitted, "paulsha-cortex · 待裁決")

    def test_build_jobs_nodes_keeps_main_row_within_the_given_width(self) -> None:
        """主行超過寬度時次要欄要整項丟棄（見 _fit_trailer），不能指望 Tree 幫忙折成
        看得懂的樣子——這件事現在由 build_jobs_nodes 的 width 參數負責，不再是面板
        渲染期折行。細節行（可複製命令）不受此限，見下一個測試。"""
        groups = group_job_rows(
            slices_from_status(
                {
                    "recent_done": [
                        {
                            "slice_id": "wf-e13fa4daae-subagent-build",
                            "gate_status": "needs_human",
                            "workflow_repo": "hamanpaul/paulsha-cortex",
                        }
                    ],
                    "degraded": False,
                }
            )
        )

        nodes = build_jobs_nodes(groups, width=_JOBS_WIDTH_FALLBACK)

        for node in nodes:
            main_text = "".join(segment_text for segment_text, _ in node.segments)
            self.assertLessEqual(_display_width(main_text), _JOBS_WIDTH_FALLBACK, main_text)

    def test_build_jobs_nodes_never_truncates_the_copyable_command(self) -> None:
        """細節行帶著可貼進終端執行的命令，截斷等於讓這個功能失去意義——
        即使給一個刻意窄的寬度，detail 也不能被砍；超寬交給 Tree 的橫向捲動。"""
        groups = group_job_rows(
            slices_from_status(
                {
                    "attention": [
                        {
                            "slice_id": "add-cortex-version-flag-build",
                            "job_state": "exited",
                            "reason": "candidate-worktree-dirty",
                            "next_actions": ["retry-build", "abandon", "retry-verify"],
                        }
                    ],
                    "degraded": False,
                }
            )
        )

        rendered = _flatten_nodes(build_jobs_nodes(groups, width=20))

        self.assertIn(
            "cortex slice-action add-cortex-version-flag-build "
            "retry-build|abandon|retry-verify --actor $USER",
            rendered,
        )
        self.assertNotIn("slice-a…", rendered)

    def test_refresh_widgets_reports_full_waiting_count_after_folding_phases(self) -> None:
        """現場回歸：6 群等人工（其中兩群各含 3~4 個 phase）＋ 大量 routine；
        捲動取代行預算後，border 仍以 slice 為單位報總量，且整棵樹一個群都不會被丟掉。"""
        app = self._minimal_app()
        widgets = {key: Mock() for key in ("#work-list", "#global-jobs")}
        waiting = []
        for run, phases in (
            ("wf-e13fa4daae", ("subagent-build", "code-review", "verification", "adversarial-review")),
            ("wf-7f4e4a8f1b", ("subagent-build", "code-review", "verification")),
            ("wf-2fa3d22552", ("subagent-build",)),
            ("wf-6f0a583d0d", ("subagent-build",)),
            ("wf-e6ad935ef9", ("adversarial-review",)),
        ):
            for phase in phases:
                waiting.append(
                    {
                        "slice_id": f"{run}-{phase}",
                        "gate_status": "needs_human",
                        "workflow_repo": "hamanpaul/paulsha-cortex",
                    }
                )
        status = {
            "ready": [f"routine-slice-{index}" for index in range(20)],
            "attention": [
                {
                    "slice_id": "add-cortex-version-flag-build",
                    "job_state": "exited",
                    "reason": "candidate-worktree-dirty",
                    "next_actions": ["retry-build"],
                }
            ],
            "recent_done": waiting,
            "degraded": False,
        }
        app.manager_client = SimpleNamespace(read_status=lambda: status)

        with patch.object(app, "query_one", side_effect=lambda sel, *a, **k: widgets[sel]):
            app._refresh_widgets()

        # 11 個 slice 收成 6 群等人工；border 仍以 slice 為單位報總量。
        self.assertEqual(widgets["#global-jobs"].border_subtitle, "31 slices · 11 待人工")

        (groups,), _ = widgets["#global-jobs"].set_groups.call_args
        rendered = _flatten_nodes(build_jobs_nodes(groups))
        for run in ("wf-e13fa4daae", "wf-7f4e4a8f1b", "wf-2fa3d22552", "wf-6f0a583d0d", "wf-e6ad935ef9"):
            self.assertIn(run, rendered, f"{run} 被丟掉了")
        self.assertIn("add-cortex-version-flag-build", rendered)
        self.assertIn("4 phase 全待裁決", rendered)
        self.assertIn("3 phase 全待裁決", rendered)

    def test_refresh_widgets_renders_degraded_jobs_panel(self) -> None:
        app = self._minimal_app()
        widgets = {key: Mock() for key in ("#work-list", "#global-jobs")}
        app.manager_client = SimpleNamespace(
            read_status=lambda: {
                "degraded": True,
                "degraded_reason": "manager-offline",
            }
        )

        with patch.object(app, "query_one", side_effect=lambda sel, *a, **k: widgets[sel]):
            app._refresh_widgets()

        self.assertEqual(widgets["#global-jobs"].border_subtitle, "degraded")
        widgets["#global-jobs"].set_message.assert_called_once()
        message_call = widgets["#global-jobs"].set_message.call_args
        self.assertIn("manager-offline", message_call.args[0])
        # degraded 訊息用琥珀色標出來，跟一般灰色說明區分開。
        style = message_call.args[1] if len(message_call.args) > 1 else message_call.kwargs.get("style")
        self.assertEqual(style, "#FBBF24")

    def test_refresh_widgets_renders_zero_slices_message(self) -> None:
        """manager 回報空 slice 清單時，JOBS 顯示單一提示列而非空白面板。"""
        app = self._minimal_app()
        widgets = {key: Mock() for key in ("#work-list", "#global-jobs")}
        app.manager_client = SimpleNamespace(read_status=lambda: {"degraded": False})

        with patch.object(app, "query_one", side_effect=lambda sel, *a, **k: widgets[sel]):
            app._refresh_widgets()

        self.assertEqual(widgets["#global-jobs"].border_subtitle, "0 slices")
        widgets["#global-jobs"].set_message.assert_called_once()
        self.assertEqual(widgets["#global-jobs"].set_message.call_args.args[0], "manager slices: 0")

    def test_manager_tick_round_trip_refreshes_open_modal_from_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"PSC_CONTROL_ROOT": tmpdir}):
            refreshed_at = contract.utcnow()
            app = self._minimal_app()
            holder = self._install_mutable_screen(app, None)
            app.push_screen = lambda screen: holder.__setitem__("screen", screen)
            started: list[dict[str, object]] = []

            class FakeThread:
                def __init__(self, *, target, daemon):
                    started.append({"target": target, "daemon": daemon, "started": False})

                def start(self):
                    started[-1]["started"] = True

            app.thread_factory = FakeThread
            app.call_from_thread = lambda callback: callback()

            app.action_manager_tick()

            self.assertEqual(len(started), 1)
            started[0]["target"]()

            request_path = next(constants.requests_dir().glob("*.json"))
            req_id = request_path.stem

            manager_daemon.run_loop(
                request_executor=lambda req: {"dispatched": ["slice-a"], "completed": [], "errors": []},
                status_provider=lambda: {
                    "ready": [],
                    "in_flight": [],
                    "recent_done": [
                        {"slice_id": "slice-a", "gate_status": "passed", "at": refreshed_at}
                    ],
                },
                periodic_tick_runner=lambda: {"dispatch_skipped": False},
                poll_interval=0.0,
                tick_interval=300.0,
                now_fn=lambda: refreshed_at,
                monotonic_fn=lambda: 0.0,
                sleep_fn=lambda _: None,
                pid=4321,
                max_rounds=1,
            )

            app.action_manager_panel()

            done = contract.read_json(constants.done_dir() / f"{req_id}.json")
            status = contract.read_json(constants.status_path())

            self.assertEqual(done["status"], "ok")
            self.assertEqual(status["recent_done"][0]["slice_id"], "slice-a")
            self.assertIsInstance(app.screen, ManagerModal)
            self.assertIn("slice-a (passed)", app.screen.status_text)
            self.assertIn(f"last_tick_at={refreshed_at}", app.screen.status_text)


class Stage11ArtifactTests(unittest.TestCase):
    def test_artifact_adapter_returns_empty_when_no_pane_hint_exists(self) -> None:
        jobs_dir = Path("tests/.stage11-artifacts")
        if jobs_dir.exists():
            shutil.rmtree(jobs_dir)
        jobs_dir.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(jobs_dir, ignore_errors=True))
        (jobs_dir / "job-1.json").write_text(
            '{"job_id": "job-1", "phase": "build", "scope": "slice-1", "trace_id": "trace-1"}',
            encoding="utf-8",
        )

        from paulshaclaw.cockpit.artifacts import ArtifactAdapter

        jobs_by_pane = ArtifactAdapter(coordinator_jobs_dir=jobs_dir).load_jobs_by_pane()

        self.assertEqual(jobs_by_pane, {})


class FakeLayoutActionService(LayoutActionService):
    def __init__(self) -> None:
        self.swaps: list[tuple[str, str]] = []
        self.focused: list[str] = []

    def swap_selected_with_active(self, *, selected_pane_id: str, active_pane_id: str) -> None:
        self.swaps.append((selected_pane_id, active_pane_id))

    def focus_pane(self, pane_id: str) -> None:
        self.focused.append(pane_id)


class DummyCockpitApp:
    def run(self) -> None:
        return None


@unittest.skipUnless(HAS_TEXTUAL, "requires textual with run_test support")
class Stage11AppTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_swaps_selected_candidate_and_focuses_new_active_pane(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={"%1": (JobSummary("registry", "running", "trace-1", "%1", "job-1"),)},
            actions=actions,
        )

        async with app.run_test() as pilot:
            await pilot.press("enter")

        self.assertEqual(actions.swaps, [("%1", "%4")])
        self.assertEqual(actions.focused, ["%1"])

    async def test_c_key_returns_focus_to_cockpit_pane(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=actions,
        )

        async with app.run_test() as pilot:
            await pilot.press("c")

        self.assertEqual(actions.focused[-1], "%0")

    async def test_question_mark_opens_help_modal(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )

        async with app.run_test() as pilot:
            await pilot.press("?")
            self.assertIsInstance(app.screen, HelpModal)

    async def test_help_modal_dismisses_on_escape(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )

        async with app.run_test() as pilot:
            await pilot.press("?")
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, HelpModal)

    async def test_down_updates_selected_pane(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )

        async with app.run_test() as pilot:
            await pilot.press("down")

        self.assertEqual(app.state.selected_pane.pane_id, "%2")

    async def test_active_row_highlight_returns_to_selected_candidate(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=actions,
        )

        async with app.run_test() as pilot:
            await pilot.press("down")
            work_list = app.query_one("#work-list")
            self.assertEqual(app.state.selected_pane.pane_id, "%2")
            self.assertEqual(work_list.index, 2)
            work_list.index = 0
            app.on_list_view_highlighted(SimpleNamespace())
            self.assertEqual(work_list.index, 2)
            await pilot.press("enter")

        self.assertEqual(actions.swaps, [("%2", "%4")])

    async def test_help_modal_blocks_background_cockpit_actions(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=actions,
        )

        async with app.run_test() as pilot:
            await pilot.press("?")
            await pilot.press("c")
            self.assertIsInstance(app.screen, HelpModal)

        self.assertEqual(actions.focused, [])

    async def test_help_modal_blocks_enter_swap(self) -> None:
        app = CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", title="cockpit", command="python", width=120, height=40),
                pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
                pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )
        actions = app.actions

        async with app.run_test() as pilot:
            await pilot.press("?")
            await pilot.press("enter")
            self.assertIsInstance(app.screen, HelpModal)

        self.assertEqual(actions.swaps, [])

    async def test_help_modal_blocks_q_and_ctrl_q(self) -> None:
        app = CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", title="cockpit", command="python", width=120, height=40),
                pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )
        with patch.object(app, "exit") as exit_mock:
            async with app.run_test() as pilot:
                await pilot.press("?")
                await pilot.press("q")
                await pilot.press("ctrl+q")
                self.assertIsInstance(app.screen, HelpModal)

        exit_mock.assert_not_called()

    async def test_manager_modal_blocks_background_bindings(self) -> None:
        actions = FakeLayoutActionService()
        submit_calls: list[tuple[str, dict[str, object], str]] = []
        app = CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", title="cockpit", command="python", width=120, height=40),
                pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=actions,
        )
        app.manager_client = SimpleNamespace(
            read_status=lambda: {
                "updated_at": "2026-07-03T12:00:00+00:00",
                "daemon": {"pid": 1234, "last_tick_at": "2026-07-03T11:59:00+00:00", "idle": False},
                "ready": ["slice-a"],
                "in_flight": [],
                "recent_done": [],
                "degraded": False,
                "degraded_reason": None,
            },
            submit_request=lambda req_type, args, requested_by: submit_calls.append((req_type, args, requested_by)) or "req-1",
        )

        with patch.object(app, "exit") as exit_mock:
            async with app.run_test() as pilot:
                await pilot.press("m")
                self.assertIsInstance(app.screen, ManagerModal)
                await pilot.press("c")
                await pilot.press("enter")
                await pilot.press("t")
                await pilot.press("q")
                await pilot.press("ctrl+q")
                self.assertIsInstance(app.screen, ManagerModal)

        self.assertEqual(actions.focused, [])
        self.assertEqual(actions.swaps, [])
        self.assertEqual(submit_calls, [])
        exit_mock.assert_not_called()

    async def test_help_modal_dismiss_triggers_light_refresh(self) -> None:
        app = CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", title="cockpit", command="python", width=120, height=40),
                pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )

        with patch.object(app, "_reconcile_state") as reconcile:
            async with app.run_test() as pilot:
                await pilot.press("?")
                await pilot.press("escape")
                self.assertNotIsInstance(app.screen, HelpModal)

        reconcile.assert_called_once_with()

    async def test_q_exits_app_through_binding(self) -> None:
        app = CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", title="cockpit", command="python", width=120, height=40),
                pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )
        with patch.object(app, "exit") as exit_mock:
            async with app.run_test() as pilot:
                await pilot.press("q")

        exit_mock.assert_called_once_with()

    async def test_ctrl_q_exits_app_through_binding(self) -> None:
        app = CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", title="cockpit", command="python", width=120, height=40),
                pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )
        with patch.object(app, "exit") as exit_mock:
            async with app.run_test() as pilot:
                await pilot.press("ctrl+q")

        exit_mock.assert_called_once_with()


class BannerComposeExtraStatLinesTests(unittest.TestCase):
    """banner 組排：當 stat 行數多於破蝦哥 art 行數（如加 cost footer），
    多出來的 stat 行仍要輸出，且左側 mascot 欄留空對齊。"""

    def _app(self) -> CockpitApp:
        return CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", session_name="main", title="cockpit", left=0, top=0, width=100, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=LayoutActionService(),
        )

    def test_extra_stat_lines_beyond_mascot_are_emitted_with_blank_left(self) -> None:
        app = self._app()
        banner = ["MASCOT1", "MASCOT2"]      # 2 mascot 行
        stats = ["s1", "s2", "s3"]           # 3 stat 行（多 1 行）
        out = app._compose_banner_stats(banner, stats).rstrip("\n").split("\n")

        self.assertEqual(len(out), 3)        # 3 行全出
        self.assertIn("s1", out[0])
        self.assertIn("MASCOT1", out[0])
        self.assertIn("s3", out[2])
        self.assertEqual(out[2].strip(), "s3")  # 多出的行：mascot 欄空白，只有 stat


class BannerCostFooterIntegrationTests(unittest.TestCase):
    """cost footer 自適應版面：banner 寬 >= 62 → 單行延伸滿 banner 寬；< 62 → cdx 併 Net
    行、cc+cpt 下一行。fail-soft：無資料時 banner 照常。"""

    def _app(self) -> CockpitApp:
        return CockpitApp.from_snapshot(
            panes=(
                pane_record("%0", session_name="main", title="cockpit", left=0, top=0, width=120, height=40),
            ),
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=LayoutActionService(),
        )

    def test_wide_banner_uses_single_full_width_line(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        app = self._app()
        with patch.object(app, "_banner_raw_width", return_value=80), patch.object(
            cost_bar, "cost_line", return_value="SINGLEMARK cc"
        ) as cline, patch.object(cost_bar, "cost_split") as csplit:
            rendered = app._brand_banner_renderable()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        self.assertIn("SINGLEMARK", text)
        csplit.assert_not_called()
        # 單行以「整個 banner 寬」渲染（cost_line 收到 full banner width 80，非 stat 欄寬）。
        cline.assert_called_once()
        self.assertEqual(cline.call_args.args[0], 80)

    def test_wide_single_line_is_right_aligned(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        app = self._app()
        with patch.object(app, "_banner_raw_width", return_value=80), patch.object(
            cost_bar, "cost_line", return_value="RIGHTCOST"  # 可見 9 字
        ), patch.object(cost_bar, "cost_split"):
            rendered = app._brand_banner_renderable()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        cost_lines = [line for line in text.split("\n") if "RIGHTCOST" in line]
        self.assertTrue(cost_lines)
        line = cost_lines[0]
        self.assertTrue(line.endswith("RIGHTCOST"))     # 靠右緣
        self.assertEqual(len(line), 80)                  # 補滿 full width
        self.assertTrue(line.startswith(" " * (80 - 9)))  # 前導 pad = 71

    def test_on_resize_refreshes_banner_for_realign(self) -> None:
        app = self._app()
        with patch.object(app, "_refresh_banner") as refresh:
            app.on_resize(None)  # resize 時立即重排（含右對齊）
        refresh.assert_called_once()

    def test_narrow_banner_splits_cdx_to_net_line(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        app = self._app()
        with patch.object(app, "_banner_raw_width", return_value=50), patch.object(
            cost_bar, "cost_split", return_value=("  | CDXMARK", "RESTMARK")
        ), patch.object(cost_bar, "cost_line") as cline:
            rendered = app._brand_banner_renderable()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        net_lines = [line for line in text.split("\n") if "Net" in line]
        self.assertTrue(net_lines, "banner 應有 Net 行")
        self.assertIn("CDXMARK", net_lines[0])
        self.assertTrue(any("RESTMARK" in line for line in text.split("\n")))
        cline.assert_not_called()

    def test_banner_ok_when_cost_unavailable(self) -> None:
        from paulshaclaw.cockpit import cost_bar

        app = self._app()
        with patch.object(cost_bar, "cost_line", return_value=None), patch.object(
            cost_bar, "cost_split", return_value=(None, None)
        ):
            rendered = app._brand_banner_renderable()  # 不應 raise
        self.assertIsNotNone(rendered)
