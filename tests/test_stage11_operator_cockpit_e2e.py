import shutil
import subprocess
import unittest
from uuid import uuid4

from paulshaclaw.cockpit.actions import LayoutActionService
from paulshaclaw.cockpit.app import CockpitApp
from paulshaclaw.cockpit.models import PaneRecord
from paulshaclaw.cockpit.tmux import TmuxClient


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
    )


class Stage11FakeMultiSessionE2ETests(unittest.TestCase):
    def test_e2e_other_session_pane_excluded_from_candidate_list(self) -> None:
        # #249 行為變更：候選清單預設收斂到 cockpit 自身 session，不再撈全 server 的他 session pane
        # （原 multi-session-listing 預設會被 13 個 session 淹沒、operator 自身 window 被埋）。
        # 他 session 的 pane（%12@work）不再出現於候選；同 session 的 pane 才是候選。
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", title="active", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%12", session_name="work", window_index="2", title="pytest", command="python", left=0, top=0, width=100, height=30),
        )

        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=LayoutActionService(),
        )

        self.assertNotIn("%12", [pane.pane_id for pane in app.state.candidate_section])
        self.assertNotIn("%12", [pane.pane_id for pane in app.state.active_section])


@unittest.skipUnless(shutil.which("tmux"), "requires tmux")
class Stage11TmuxE2ETests(unittest.TestCase):
    def _list_session_panes(
        self,
        client: TmuxClient,
        *,
        session_name: str,
        cockpit_pane_id: str,
    ) -> tuple[PaneRecord, ...]:
        return tuple(
            pane
            for pane in client.list_panes(cockpit_pane_id=cockpit_pane_id)
            if pane.session_name == session_name
        )

    def test_app_swap_reconciles_active_slot_focuses_selected_and_returns_to_cockpit(self) -> None:
        session_name = f"stage11-e2e-{uuid4().hex[:8]}"
        cockpit_pane_id = self._tmux(
            "new-session",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-s",
            session_name,
            "-x",
            "200",
            "-y",
            "80",
            "bash",
        )
        self.addCleanup(self._kill_session, session_name)
        self._tmux("split-window", "-d", "-P", "-F", "#{pane_id}", "-h", "-t", cockpit_pane_id, "bash")
        self._tmux("split-window", "-d", "-P", "-F", "#{pane_id}", "-v", "-t", cockpit_pane_id, "bash")

        client = TmuxClient()
        initial_panes = self._list_session_panes(
            client,
            session_name=session_name,
            cockpit_pane_id=cockpit_pane_id,
        )
        app = CockpitApp.from_snapshot(
            panes=initial_panes,
            cockpit_pane_id=cockpit_pane_id,
            cockpit_session_name=session_name,
            jobs_by_pane={},
            actions=LayoutActionService(session_target=session_name),
            pane_loader=lambda *, cockpit_pane_id: self._list_session_panes(
                client,
                session_name=session_name,
                cockpit_pane_id=cockpit_pane_id,
            ),
        )

        state = app.state
        active = state.active_pane
        selected = state.selected_pane
        self.assertIsNotNone(active)
        self.assertIsNotNone(selected)
        assert active is not None
        assert selected is not None

        selected_anchor = selected.anchor
        active_anchor = active.anchor

        app.action_swap_selected()
        self.assertEqual(app.state.active_pane.pane_id, selected.pane_id)
        self.assertEqual(self._pane_by_id(app.state.panes, selected.pane_id).anchor, active_anchor)
        self.assertEqual(self._pane_by_id(app.state.panes, active.pane_id).anchor, selected_anchor)
        self.assertEqual(self._focused_pane_id(session_name), selected.pane_id)

        app.action_focus_cockpit()
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

    def _tmux(self, *args: str) -> str:
        completed = subprocess.run(
            ["tmux", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
