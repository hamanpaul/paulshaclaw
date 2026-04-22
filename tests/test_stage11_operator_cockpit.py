import subprocess
import sys
import unittest

from textual.pilot import Pilot

from paulshaclaw.cockpit.actions import LayoutActionService
from paulshaclaw.cockpit.app import CockpitApp
from paulshaclaw.cockpit.models import JobSummary, PaneRecord


class FakeLayoutActionService(LayoutActionService):
    def __init__(self) -> None:
        self.swaps: list[tuple[str, str]] = []
        self.focused: list[str] = []

    def swap_selected_with_active(self, *, selected_pane_id: str, active_pane_id: str) -> None:
        self.swaps.append((selected_pane_id, active_pane_id))

    def focus_pane(self, pane_id: str) -> None:
        self.focused.append(pane_id)


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
