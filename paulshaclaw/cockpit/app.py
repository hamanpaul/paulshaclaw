from __future__ import annotations

from textual.app import App
from textual.widgets import Footer, Header, Static


class CockpitApp(App[None]):
    """Minimal Stage 11 shell; real widgets arrive in later tasks."""

    TITLE = "PaulShiaBro Stage 11 Cockpit"

    def compose(self):
        yield Header()
        yield Static("Stage 11 operator cockpit bootstrap", id="stage11-bootstrap")
        yield Footer()
