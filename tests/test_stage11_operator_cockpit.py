import subprocess
import shutil
import sys
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
from paulshaclaw.cockpit.app import REFRESH_INTERVAL_SECONDS, CockpitApp, pane_display_label
from paulshaclaw.cockpit.help import HelpModal
from paulshaclaw.cockpit.models import JobSummary, PaneRecord, SlotAnchor
from paulshaclaw.cockpit.store import CockpitState, choose_startup_slot
from paulshaclaw.cockpit.tmux import TmuxClient, derive_summary, parse_list_panes


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

    def test_main_derives_cockpit_session_from_pane_record(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", session_name="main", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%9", session_name="work", title="pytest", command="python", width=80, height=20),
        )
        with (
            patch.object(TmuxClient, "list_panes", return_value=panes),
            patch("paulshaclaw.cockpit.__main__.ArtifactAdapter") as adapter_class,
            patch.object(CockpitApp, "from_snapshot", return_value=DummyCockpitApp()) as from_snapshot,
        ):
            adapter_class.return_value.load_jobs_by_pane.return_value = {}
            exit_code = cockpit_main.main(["--cockpit-pane", "%0"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(from_snapshot.call_args.kwargs["cockpit_session_name"], "main")

    def test_main_returns_zero_on_once_flag_without_starting_ui(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", session_name="main", title="ssh", command="bash", left=120, width=120, height=40),
        )
        with (
            patch.object(TmuxClient, "list_panes", return_value=panes),
            patch("paulshaclaw.cockpit.__main__.ArtifactAdapter") as adapter_class,
            patch.object(CockpitApp, "from_snapshot") as from_snapshot,
        ):
            adapter_class.return_value.load_jobs_by_pane.return_value = {}
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

    def test_pane_display_label_includes_session_window(self) -> None:
        pane = pane_record("%12", session_name="work", window_index="2", title="pytest")

        self.assertEqual(pane_display_label(pane), "work:2 %12 pytest")

    def test_pane_display_label_falls_back_to_derived_summary(self) -> None:
        pane = PaneRecord(
            pane_id="%0", session_name="main", window_index="0", title="", command="minicom",
            left=0, top=0, width=80, height=24, active=False, preview=(),
            pane_tty="/dev/pts/2", summary="minicom COM0",
        )

        self.assertEqual(pane_display_label(pane), "main:0 %0 minicom COM0")

    def test_derive_summary_minicom_reads_com_from_process(self) -> None:
        pane = pane_record("%0", title="", command="minicom")
        pane = PaneRecord(**{**pane.__dict__, "pane_tty": "/dev/pts/2"})
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="  minicom -D /dev/pts/17 --color=on -C /home/x/b-log/mini_COM0_260610.log\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "minicom COM0")

    def test_derive_summary_non_minicom_empty_title_uses_command(self) -> None:
        pane = pane_record("%9", title="", command="node")
        self.assertEqual(derive_summary(pane), "[node]")

    def test_derive_summary_prefers_pane_title(self) -> None:
        pane = pane_record("%3", title="Debug thing", command="claude")
        self.assertEqual(derive_summary(pane), "Debug thing")

    def test_parse_list_panes_reads_pane_tty(self) -> None:
        raw = "%0\tmain\t0\t\tminicom\t0\t0\t120\t40\t1\t/dev/pts/7\n"
        panes = parse_list_panes(raw)
        self.assertEqual(panes[0].pane_tty, "/dev/pts/7")
        self.assertEqual(panes[0].command, "minicom")

    def test_on_mount_schedules_periodic_refresh(self) -> None:
        app = self._minimal_app()
        with patch.object(app, "_refresh_widgets"), patch.object(app, "set_interval") as set_interval:
            app.on_mount()
        set_interval.assert_called_once()
        self.assertEqual(set_interval.call_args.args[0], REFRESH_INTERVAL_SECONDS)
        self.assertEqual(set_interval.call_args.args[1], app._on_refresh_tick)

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
        widgets = {key: Mock() for key in ("#active-slot", "#work-list", "#pane-detail", "#global-jobs")}

        with patch.object(app, "query_one", side_effect=lambda sel, *a, **k: widgets[sel]):
            app._refresh_widgets()
            app._refresh_widgets()  # identical content -> list not rebuilt again
            self.assertEqual(widgets["#work-list"].clear.call_count, 1)
            # detail keeps updating every refresh even when the list is unchanged
            self.assertGreaterEqual(widgets["#pane-detail"].update.call_count, 2)

            app.state = app.state.move_selection(1)  # cursor moves to a different candidate
            app._refresh_widgets()
            self.assertEqual(widgets["#work-list"].clear.call_count, 2)

    def test_light_refresh_reloads_panes_without_previews(self) -> None:
        seen: dict[str, object] = {}

        def loader(*, cockpit_pane_id: str, capture_previews: bool = True):
            seen["capture_previews"] = capture_previews
            return self._minimal_panes()

        app = self._minimal_app(pane_loader=loader)
        with patch.object(app, "_refresh_widgets"):
            app._reconcile_state(light=True)
        self.assertIs(seen["capture_previews"], False)

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

    def test_candidate_section_sorts_window_index_numerically(self) -> None:
        panes = (
            pane_record("%0", session_name="main", window_index="0", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", window_index="0", left=120, top=0, width=120, height=40),
            pane_record("%10", session_name="alpha", window_index="10", left=0, top=0, width=80, height=20),
            pane_record("%2", session_name="alpha", window_index="2", left=0, top=0, width=80, height=20),
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

    def test_help_modal_lists_all_bindings(self) -> None:
        help_text = HelpModal.render_help_text(CockpitApp.BINDINGS)

        self.assertIn("up: ↑/↓ 選擇", help_text)
        self.assertIn("down: ↑/↓ 選擇", help_text)
        self.assertIn("enter: Enter 把選中的 pane 換到我面前", help_text)
        self.assertIn("c: c 回 cockpit", help_text)
        self.assertIn("q: q 離開 cockpit", help_text)
        self.assertIn("ctrl+q: Ctrl+Q 離開 cockpit", help_text)
        self.assertIn("question_mark: ? 顯示說明", help_text)
        self.assertIn("all local tmux sessions", help_text)


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
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40, preview=("active",)),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20, preview=("job 1",)),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20, preview=("traffic",)),
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

    async def test_down_updates_selected_preview_target(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=80, height=20, preview=("job 1",)),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20, preview=("traffic",)),
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

    async def test_active_row_highlight_snaps_back_to_first_candidate(self) -> None:
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
            await pilot.press("up")
            work_list = app.query_one("#work-list")
            self.assertEqual(work_list.index, 1)
            await pilot.press("enter")

        self.assertEqual(actions.swaps, [("%1", "%4")])

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

    def test_q_and_ctrl_q_have_explicit_quit_paths(self) -> None:
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
            app.on_key(SimpleNamespace(key="q"))
            app.on_key(SimpleNamespace(key="ctrl+q"))

        self.assertEqual(exit_mock.call_count, 2)
