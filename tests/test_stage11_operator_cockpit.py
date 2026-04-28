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
    preview: tuple[str, ...] = (),
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
        preview=preview,
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

    def test_main_exits_with_error_when_cockpit_pane_is_missing(self) -> None:
        stderr = StringIO()
        with patch.object(TmuxClient, "list_panes", return_value=()), patch("sys.stderr", stderr):
            exit_code = cockpit_main.main(["--cockpit-pane", "%404"])

        self.assertEqual(exit_code, 1)
        self.assertIn("cockpit pane not found: %404", stderr.getvalue())


class Stage11StateTests(unittest.TestCase):
    def test_parse_list_panes_extracts_geometry(self) -> None:
        raw = "%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\n%4\tmain\t1\tssh\tbash\t120\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual(panes[0].pane_id, "%0")
        self.assertEqual(panes[0].session_name, "main")
        self.assertEqual(panes[0].window_index, "0")
        self.assertEqual(panes[1].left, 120)
        self.assertEqual(panes[1].width, 120)

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

    def test_list_panes_uses_dash_a_flag(self) -> None:
        client = TmuxClient()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\t1\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed) as run_mock:
            panes = client.list_panes(cockpit_pane_id="%0")

        command = run_mock.call_args.args[0]
        self.assertEqual(command[:3], ["tmux", "list-panes", "-a"])
        self.assertNotIn("-t", command)
        self.assertIn("#{session_name}", command[-1])
        self.assertIn("#{window_index}", command[-1])
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
        self.assertIn("%9", [pane.pane_id for pane in state.candidate_section])

    def test_candidate_section_sorted_by_session_window_pane(self) -> None:
        panes = (
            pane_record("%0", session_name="main", window_index="0", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", window_index="0", left=120, top=0, width=120, height=40),
            pane_record("%7", session_name="beta", window_index="2", left=0, top=0, width=80, height=20),
            pane_record("%3", session_name="alpha", window_index="1", left=0, top=0, width=80, height=20),
            pane_record("%2", session_name="beta", window_index="1", left=0, top=0, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.candidate_section], ["%3", "%2", "%7"])

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
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40, preview=("active",)),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20, preview=("job 1",)),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20, preview=("traffic",)),
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
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20),
        )
        actions = FakeLayoutActionService()
        app = CockpitApp.from_snapshot(panes=panes, cockpit_pane_id="%0", jobs_by_pane={}, actions=actions)

        async with app.run_test() as pilot:
            await pilot.press("c")

        self.assertEqual(actions.focused[-1], "%0")
