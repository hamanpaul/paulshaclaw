import shutil
import subprocess
import unittest
from uuid import uuid4

from paulshaclaw.cockpit.actions import LayoutActionService
from paulshaclaw.cockpit.store import CockpitState
from paulshaclaw.cockpit.tmux import TmuxClient


@unittest.skipUnless(shutil.which("tmux"), "requires tmux")
class Stage11TmuxE2ETests(unittest.TestCase):
    def test_swap_reconciles_active_slot_focuses_selected_and_returns_to_cockpit(self) -> None:
        session_name = f"stage11-e2e-{uuid4().hex[:8]}"
        self._tmux("new-session", "-d", "-s", session_name, "-x", "200", "-y", "80", "bash")
        self.addCleanup(self._kill_session, session_name)
        self._tmux("split-window", "-h", "-t", f"{session_name}:0.0", "bash")
        self._tmux("split-window", "-v", "-t", f"{session_name}:0.0", "bash")

        cockpit_pane_id = self._pane_id_for_target(f"{session_name}:0.0")
        client = TmuxClient(session_name=session_name)
        initial_panes = client.list_panes(cockpit_pane_id=cockpit_pane_id)
        state = CockpitState.from_panes(initial_panes, cockpit_pane_id=cockpit_pane_id)
        actions = LayoutActionService(session_target=session_name)

        active = state.active_pane
        selected = state.selected_pane
        self.assertIsNotNone(active)
        self.assertIsNotNone(selected)
        assert active is not None
        assert selected is not None

        selected_anchor = selected.anchor
        active_anchor = active.anchor

        actions.swap_selected_with_active(
            selected_pane_id=selected.pane_id,
            active_pane_id=active.pane_id,
        )

        reconciled = state.refresh(client.list_panes(cockpit_pane_id=cockpit_pane_id))
        self.assertEqual(reconciled.active_pane.pane_id, selected.pane_id)
        self.assertEqual(self._pane_by_id(reconciled.panes, selected.pane_id).anchor, active_anchor)
        self.assertEqual(self._pane_by_id(reconciled.panes, active.pane_id).anchor, selected_anchor)

        actions.focus_pane(selected.pane_id)
        self.assertEqual(self._focused_pane_id(session_name), selected.pane_id)

        actions.return_to_cockpit(cockpit_pane_id)
        self.assertEqual(self._focused_pane_id(session_name), cockpit_pane_id)

    def _focused_pane_id(self, session_name: str) -> str:
        return self._tmux("display-message", "-p", "-t", session_name, "#{pane_id}")

    def _kill_session(self, session_name: str) -> None:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            check=False,
            capture_output=True,
            text=True,
        )

    def _pane_by_id(self, panes, pane_id: str):
        for pane in panes:
            if pane.pane_id == pane_id:
                return pane
        self.fail(f"pane not found: {pane_id}")

    def _pane_id_for_target(self, target: str) -> str:
        return self._tmux("display-message", "-p", "-t", target, "#{pane_id}")

    def _tmux(self, *args: str) -> str:
        completed = subprocess.run(
            ["tmux", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
