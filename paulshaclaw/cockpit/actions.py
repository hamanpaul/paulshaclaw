from __future__ import annotations

import subprocess


class LayoutActionService:
    def __init__(self, *, session_target: str | None = None) -> None:
        self.session_target = session_target

    def swap_selected_with_active(self, *, selected_pane_id: str, active_pane_id: str) -> None:
        subprocess.run(
            ["tmux", "swap-pane", "-s", selected_pane_id, "-t", active_pane_id],
            check=True,
            capture_output=True,
            text=True,
        )

    def focus_pane(self, pane_id: str) -> None:
        subprocess.run(
            ["tmux", "select-pane", "-t", pane_id],
            check=True,
            capture_output=True,
            text=True,
        )

    def return_to_cockpit(self, cockpit_pane_id: str) -> None:
        self.focus_pane(cockpit_pane_id)
