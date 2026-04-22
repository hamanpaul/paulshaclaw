from __future__ import annotations

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, ListItem, ListView, Static
except Exception:  # pragma: no cover - fallback when textual not installed
    # Minimal stubs so module is importable without textual installed.
    from typing import Any, Generic, Iterable, TypeVar

    T = TypeVar("T")

    class App(Generic[T]):
        pass

    ComposeResult = Iterable[Any]

    class Binding:  # pragma: no cover - noop
        def __init__(self, key: str, handler: str, description: str) -> None:
            self.key = key
            self.handler = handler
            self.description = description

    class _Container:  # pragma: no cover - noop
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

    Horizontal = Vertical = _Container

    class _Widget:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    Footer = Header = Static = _Widget

    class ListItem(_Widget):
        pass

    class ListView(_Widget):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__()
        def clear(self) -> None:  # pragma: no cover - noop
            pass
        def append(self, item: Any) -> None:  # pragma: no cover - noop
            pass

from .actions import LayoutActionService
from .models import JobSummary, PaneRecord
from .store import CockpitState


class CockpitApp(App[None]):
    TITLE = "PaulShiaBro Stage 11 Cockpit"
    BINDINGS = [
        Binding("up", "move_up", "Up"),
        Binding("down", "move_down", "Down"),
        Binding("enter", "swap_selected", "Swap"),
        Binding("c", "focus_cockpit", "Cockpit"),
    ]

    def __init__(self, *, state: CockpitState, jobs_by_pane: dict[str, tuple[JobSummary, ...]], actions: LayoutActionService) -> None:
        super().__init__()
        self.state = state
        self.jobs_by_pane = jobs_by_pane
        self.actions = actions

    @classmethod
    def from_snapshot(
        cls,
        *,
        panes: tuple[PaneRecord, ...],
        cockpit_pane_id: str,
        jobs_by_pane: dict[str, tuple[JobSummary, ...]],
        actions: LayoutActionService,
    ) -> "CockpitApp":
        return cls(
            state=CockpitState.from_panes(panes, cockpit_pane_id=cockpit_pane_id),
            jobs_by_pane=jobs_by_pane,
            actions=actions,
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Static("", id="active-slot")
                yield ListView(id="work-list")
            with Vertical(id="right-pane"):
                yield Static("", id="pane-detail")
                yield Static("", id="global-jobs")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_widgets()
        # Ensure a focusable widget is focused so Pilot key presses reach the app
        try:
            work_list = self.query_one("#work-list", ListView)
            work_list.focus()
        except Exception:
            # fallback stubs may not support focus; ignore
            pass

    def action_move_up(self) -> None:
        self.state = self.state.move_selection(-1)
        self._refresh_widgets()

    def action_move_down(self) -> None:
        self.state = self.state.move_selection(1)
        self._refresh_widgets()

    def action_swap_selected(self) -> None:
        active_pane = self.state.active_pane
        selected_pane = self.state.selected_pane
        if active_pane is None or selected_pane is None:
            return
        self.actions.swap_selected_with_active(
            selected_pane_id=selected_pane.pane_id,
            active_pane_id=active_pane.pane_id,
        )
        self.actions.focus_pane(selected_pane.pane_id)

    def action_focus_cockpit(self) -> None:
        self.actions.focus_pane(self.state.cockpit_pane_id)

    def on_key(self, event: object) -> None:
        # Pilot key events are delivered as objects with either `key` or
        # `character` attributes depending on Textual version. Handle only
        # those explicit attributes and dispatch the small set of keys we
        # need for the tests. This keeps the compatibility path narrow and
        # avoids swallowing unrelated errors.
        try:
            if hasattr(event, "key"):
                key = event.key
            elif hasattr(event, "character"):
                key = event.character
            else:
                return
        except AttributeError:
            # If event is a strange object without expected attributes,
            # don't attempt to handle it.
            return

        if key == "enter" or key == "\r":
            self.action_swap_selected()
        elif key == "c":
            self.action_focus_cockpit()

    def _refresh_widgets(self) -> None:
        active = self.state.active_pane
        active_text = "<missing>" if active is None else f"ACTIVE {active.pane_id} {active.title} {active.command}"
        self.query_one("#active-slot", Static).update(active_text)

        work_list = self.query_one("#work-list", ListView)
        work_list.clear()
        if active is not None:
            work_list.append(ListItem(Static(f"[ACTIVE] {active.pane_id} {active.title}")))
        for pane in self.state.candidate_section:
            prefix = ">" if self.state.selected_pane and pane.pane_id == self.state.selected_pane.pane_id else " "
            work_list.append(ListItem(Static(f"{prefix} {pane.pane_id} {pane.title}")))

        selected = self.state.selected_pane
        if selected is None:
            detail_text = "No candidate panes"
        else:
            jobs = self.jobs_by_pane.get(selected.pane_id, ())
            detail_text = "\n".join(
                [f"{selected.pane_id} {selected.title}", *selected.preview, *(job.status for job in jobs)]
            )
        self.query_one("#pane-detail", Static).update(detail_text)
        all_jobs = [job for items in self.jobs_by_pane.values() for job in items]
        if all_jobs:
            global_jobs_text = "\n".join(
                f"{job.pane_id or '-'} {job.status} {job.trace_id or '-'}"
                for job in all_jobs[:10]
            )
        else:
            global_jobs_text = "jobs loaded: 0"
        self.query_one("#global-jobs", Static).update(global_jobs_text)
