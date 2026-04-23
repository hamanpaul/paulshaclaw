import subprocess
import shutil
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# textual is an optional dev/test dependency. Guard imports so the repository's
# baseline tests (python -m unittest discover) can run under system Python
# without textual installed. The UI tests will be skipped when textual is
# unavailable and run when a dev venv provides textual.
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
from paulshaclaw.cockpit.app import CockpitApp
from paulshaclaw.cockpit.models import JobSummary, PaneRecord, SlotAnchor
from paulshaclaw.cockpit.store import CockpitState, choose_startup_slot
from paulshaclaw.cockpit.tmux import TmuxClient, parse_list_panes


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

    def test_main_exits_with_error_when_cockpit_pane_is_missing(self) -> None:
        stderr = StringIO()
        with patch.object(TmuxClient, "list_panes", return_value=()), patch("sys.stderr", stderr):
            exit_code = cockpit_main.main(["--cockpit-pane", "%404"])

        self.assertEqual(exit_code, 1)
        self.assertIn("cockpit pane not found: %404", stderr.getvalue())


class Stage11StateTests(unittest.TestCase):
    def test_parse_list_panes_extracts_geometry(self) -> None:
        raw = "%0\tcockpit\tpython\t0\t0\t120\t40\n%4\tssh\tbash\t120\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual(panes[0].pane_id, "%0")
        self.assertEqual(panes[1].left, 120)
        self.assertEqual(panes[1].width, 120)

    def test_parse_list_panes_skips_malformed_numeric_fields(self) -> None:
        raw = "%0\tcockpit\tpython\t0\t0\t120\t40\n%4\tssh\tbash\tnan\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual([pane.pane_id for pane in panes], ["%0"])

    def test_tmux_client_returns_empty_when_tmux_list_panes_fails(self) -> None:
        client = TmuxClient()
        with patch("paulshaclaw.cockpit.tmux.subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.CalledProcessError(1, ["tmux", "list-panes"])

            panes = client.list_panes(cockpit_pane_id="%0")

        self.assertEqual(panes, ())

    def test_choose_startup_slot_excludes_cockpit_even_when_same_size(self) -> None:
        panes = (
            PaneRecord("%0", "cockpit", "python", 0, 0, 120, 40, False, ()),
            PaneRecord("%4", "ssh", "bash", 120, 0, 120, 40, False, ()),
            PaneRecord("%1", "agent1", "node", 0, 40, 80, 20, False, ()),
        )

        anchor = choose_startup_slot(panes, cockpit_pane_id="%0")

        self.assertEqual(anchor, SlotAnchor(left=120, top=0, width=120, height=40))

    def test_state_segments_active_and_candidate_sections(self) -> None:
        panes = (
            PaneRecord("%0", "cockpit", "python", 0, 0, 120, 40, False, ()),
            PaneRecord("%4", "ssh", "bash", 120, 0, 120, 40, False, ()),
            PaneRecord("%1", "agent1", "node", 0, 40, 80, 20, False, ()),
            PaneRecord("%2", "iperf", "iperf3", 80, 40, 80, 20, False, ()),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0")

        self.assertEqual([pane.pane_id for pane in state.active_section], ["%4"])
        self.assertEqual([pane.pane_id for pane in state.candidate_section], ["%1", "%2"])

    def test_state_marks_active_slot_lost_when_no_pane_matches_anchor(self) -> None:
        panes = (
            PaneRecord("%0", "cockpit", "python", 0, 0, 120, 40, False, ()),
            PaneRecord("%1", "agent1", "node", 0, 40, 80, 20, False, ()),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0")
        shifted = (
            PaneRecord("%0", "cockpit", "python", 0, 0, 120, 40, False, ()),
            PaneRecord("%1", "agent1", "node", 80, 40, 80, 20, False, ()),
        )

        degraded = state.refresh(shifted)

        self.assertEqual(degraded.degraded_reason, "active-slot-lost")
        self.assertEqual(degraded.active_section, ())


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


@unittest.skipUnless(HAS_TEXTUAL, "requires textual with run_test support")
class Stage11AppTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_swaps_selected_candidate_and_focuses_new_active_pane(self) -> None:
        panes = (
            PaneRecord("%0", "cockpit", "python", 0, 0, 120, 40, False, ()),
            PaneRecord("%4", "ssh", "bash", 120, 0, 120, 40, False, ("active",)),
            PaneRecord("%1", "agent1", "node", 0, 40, 80, 20, False, ("job 1",)),
            PaneRecord("%2", "iperf", "iperf3", 80, 40, 80, 20, False, ("traffic",)),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            jobs_by_pane={"%1": (JobSummary("registry", "running", "trace-1", "%1", "job-1"),)},
            actions=actions,
        )

        async with app.run_test() as pilot:
            await pilot.press("enter")

        self.assertEqual(actions.swaps, [("%1", "%4")])
        self.assertEqual(actions.focused, ["%1"])

    async def test_c_key_returns_focus_to_cockpit_pane(self) -> None:
        panes = (
            PaneRecord("%0", "cockpit", "python", 0, 0, 120, 40, False, ()),
            PaneRecord("%4", "ssh", "bash", 120, 0, 120, 40, False, ()),
            PaneRecord("%1", "agent1", "node", 0, 40, 80, 20, False, ()),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(panes=panes, cockpit_pane_id="%0", jobs_by_pane={}, actions=actions)

        async with app.run_test() as pilot:
            await pilot.press("c")

        self.assertEqual(actions.focused[-1], "%0")
