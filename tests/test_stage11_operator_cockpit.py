import subprocess
import sys
import unittest


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


from paulshaclaw.cockpit.models import PaneRecord, SlotAnchor
from paulshaclaw.cockpit.store import CockpitState, choose_startup_slot
from paulshaclaw.cockpit.tmux import parse_list_panes


class Stage11StateTests(unittest.TestCase):
    def test_parse_list_panes_extracts_geometry(self) -> None:
        raw = "%0\tcockpit\tpython\t0\t0\t120\t40\n%4\tssh\tbash\t120\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual(panes[0].pane_id, "%0")
        self.assertEqual(panes[1].left, 120)
        self.assertEqual(panes[1].width, 120)

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
