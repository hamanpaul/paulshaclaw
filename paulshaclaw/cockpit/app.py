from __future__ import annotations

from collections.abc import Callable

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
from .help import HelpModal
from .models import JobSummary, PaneRecord
from .store import CockpitState


def pane_display_label(pane: PaneRecord) -> str:
    return f"{pane.session_name}:{pane.window_index} {pane.pane_id} {pane.display_summary}"


# How often the cockpit re-reads the tmux pane list so the work summary stays
# live. Each tick is bounded (one `list-panes`, a tiny `ps` only for title-less
# minicom panes, and one preview capture for the selected pane) — no large or
# growing reads, so it can't pile up the way an unbounded scan would.
REFRESH_INTERVAL_SECONDS = 3.0


class CockpitApp(App[None]):
    TITLE = "PaulShiaBro Stage 11 Cockpit"
    BINDINGS = [
        Binding("up", "move_up", "↑/↓ 選擇"),
        Binding("down", "move_down", "↑/↓ 選擇"),
        Binding("enter", "swap_selected", "Enter 把選中的 pane 換到我面前"),
        Binding("c", "focus_cockpit", "c 回 cockpit"),
        Binding("question_mark", "show_help", "? 顯示說明"),
    ]

    def __init__(
        self,
        *,
        state: CockpitState,
        jobs_by_pane: dict[str, tuple[JobSummary, ...]],
        actions: LayoutActionService,
        pane_loader: Callable[..., tuple[PaneRecord, ...]] | None = None,
        preview_loader: Callable[[str], tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.jobs_by_pane = jobs_by_pane
        self.actions = actions
        self.pane_loader = pane_loader
        self.preview_loader = preview_loader

    @classmethod
    def from_snapshot(
        cls,
        *,
        panes: tuple[PaneRecord, ...],
        cockpit_pane_id: str,
        cockpit_session_name: str,
        jobs_by_pane: dict[str, tuple[JobSummary, ...]],
        actions: LayoutActionService,
        pane_loader: Callable[..., tuple[PaneRecord, ...]] | None = None,
        preview_loader: Callable[[str], tuple[str, ...]] | None = None,
    ) -> "CockpitApp":
        return cls(
            state=CockpitState.from_panes(
                panes,
                cockpit_pane_id=cockpit_pane_id,
                cockpit_session_name=cockpit_session_name,
            ),
            jobs_by_pane=jobs_by_pane,
            actions=actions,
            pane_loader=pane_loader,
            preview_loader=preview_loader,
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
        # Keep the work list live: re-read panes on a fixed interval (bounded
        # work — see REFRESH_INTERVAL_SECONDS). Guarded for the textual stub.
        try:
            self.set_interval(REFRESH_INTERVAL_SECONDS, self._on_refresh_tick)
        except Exception:
            pass
        # Ensure a focusable widget is focused so Pilot key presses reach the app
        try:
            work_list = self.query_one("#work-list", ListView)
            work_list.focus()
        except Exception:
            # fallback stubs may not support focus; ignore
            pass

    def _on_refresh_tick(self) -> None:
        self._reconcile_state(light=True)

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
        self._reconcile_state()

    def action_focus_cockpit(self) -> None:
        self.actions.return_to_cockpit(self.state.cockpit_pane_id)

    def action_show_help(self) -> None:
        self.push_screen(HelpModal(self.BINDINGS))

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
        elif key == "?" or key == "question_mark":
            self.action_show_help()

    def _reconcile_state(self, *, light: bool = False) -> None:
        if self.pane_loader is None:
            return
        # The periodic (light) reload skips per-pane preview captures; the detail
        # view captures the selected pane's preview on demand instead, so a tick
        # is one list-panes call regardless of how many panes exist.
        try:
            if light:
                panes = self.pane_loader(
                    cockpit_pane_id=self.state.cockpit_pane_id, capture_previews=False
                )
            else:
                panes = self.pane_loader(cockpit_pane_id=self.state.cockpit_pane_id)
        except TypeError:
            panes = self.pane_loader(cockpit_pane_id=self.state.cockpit_pane_id)
        self.state = self.state.refresh(panes)
        try:
            self._refresh_widgets()
        except Exception:
            pass

    def _selected_preview(self, pane: PaneRecord) -> tuple[str, ...]:
        if self.preview_loader is not None and pane.pane_id != self.state.cockpit_pane_id:
            try:
                return self.preview_loader(pane.pane_id)
            except Exception:
                return pane.preview
        return pane.preview

    def _refresh_widgets(self) -> None:
        active = self.state.active_pane
        active_text = (
            "<missing>"
            if active is None
            else f"ACTIVE {pane_display_label(active)} {active.command}"
        )
        self.query_one("#active-slot", Static).update(active_text)

        work_list = self.query_one("#work-list", ListView)
        work_list.clear()
        if active is not None:
            work_list.append(ListItem(Static(f"[ACTIVE] {pane_display_label(active)}")))
        for pane in self.state.candidate_section:
            prefix = ">" if self.state.selected_pane and pane.pane_id == self.state.selected_pane.pane_id else " "
            work_list.append(ListItem(Static(f"{prefix} {pane_display_label(pane)}")))

        selected = self.state.selected_pane
        if selected is None:
            detail_text = "\n".join(
                [
                    "No candidate panes",
                    f"state: {self.state.degraded_reason or 'ok'}",
                ]
            )
        else:
            jobs = self.jobs_by_pane.get(selected.pane_id, ())
            if jobs:
                job_lines = [f"{job.source}:{job.status}:{job.trace_id or '-'}" for job in jobs]
            else:
                job_lines = ["job-state: unmapped"]
            detail_text = "\n".join(
                [
                    f"{selected.pane_id} {selected.display_summary}",
                    *self._selected_preview(selected),
                    *job_lines,
                    f"state: {self.state.degraded_reason or 'ok'}",
                ]
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
