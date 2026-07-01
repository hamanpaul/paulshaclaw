from __future__ import annotations

import inspect
from collections.abc import Callable

from . import branding, sysmon

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
# live. Kept at 30s so the periodic redraw isn't a visible flicker; each tick is
# bounded anyway (one `list-panes`, a tiny `ps` only for title-less minicom
# panes, and one preview capture for the selected pane) — no large or growing
# reads, so it can't pile up the way an unbounded scan would.
REFRESH_INTERVAL_SECONDS = 30.0


class CockpitApp(App[None]):
    TITLE = "PaulShiaBro Stage 11 Cockpit"
    BINDINGS = [
        Binding("up", "move_up", "↑/↓ 選擇"),
        Binding("down", "move_down", "↑/↓ 選擇"),
        Binding("enter", "swap_selected", "Enter 把選中的 pane 換到我面前"),
        Binding("c", "focus_cockpit", "c 回 cockpit"),
        Binding("q", "quit_app", "q 離開 cockpit"),
        Binding("ctrl+q", "quit_app", "Ctrl+Q 離開 cockpit"),
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
        # 系統監控（banner 右側 htop 風）：CPU%/IO%/Net 速率需前後快照差值，故保留上次快照；
        # _last_stats 存最後有效讀數，None 時沿用以避免快速重刷閃爍。
        self._mon_prev = None
        self._last_stats: dict = {}   # 最後有效讀數（bridge 偶發缺樣）
        self._stale: dict = {}        # 各項連續缺樣次數（超過容忍即降級為 '--'）
        # Last-rendered work-list content, so we skip rebuilding (and flickering)
        # the list on refreshes that didn't change it.
        self._last_work_items: tuple[str, ...] | None = None

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
        yield Static("", id="brand-banner")  # 破蝦哥 🦞 banner（issue #116）；內容於 on_mount 填入
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Static("", id="active-slot")
                yield ListView(id="work-list")
            with Vertical(id="right-pane"):
                yield Static("", id="pane-detail")
                yield Static("", id="global-jobs")
        yield Footer()

    def on_mount(self) -> None:
        # 吉祥物（破蝦哥 🦞）品牌（issue #116）：標題前綴 + 置頂 banner C。皆 fail-soft，絕不擋 TUI 啟動。
        try:
            self.title = branding.cockpit_title()
        except Exception:
            pass
        # brand-banner（+ 系統監控）由 _refresh_widgets 統一填入並每 tick 刷新。
        self._refresh_widgets()
        # Keep the work list live: re-read panes on a fixed interval (bounded
        # work — see REFRESH_INTERVAL_SECONDS). The textual stub has no
        # set_interval; only that absence is tolerated, real errors surface.
        try:
            self.set_interval(REFRESH_INTERVAL_SECONDS, self._on_refresh_tick)
        except AttributeError:
            pass
        # Ensure a focusable widget is focused so Pilot key presses reach the app
        try:
            work_list = self.query_one("#work-list", ListView)
            work_list.focus()
        except Exception:
            # fallback stubs may not support focus; ignore
            pass

    _MON_COL = 15   # banner 各列補到的固定可見寬
    _MON_GAP = 2    # banner 與監控列間距

    def _brand_banner_renderable(self):
        """破蝦哥 banner C + 右側 htop 風系統監控（CPU/Mem/Swp/I/O 橫條 + Net 速率）。

        橫條寬隨終端寬度自適應；監控 fail-soft：讀 /proc 失敗則只顯示 banner。
        """
        banner_lines = branding.banner("c").rstrip("\n").split("\n")
        stat_lines: list[str] = []
        try:
            cur = sysmon.read_snapshot()
            stats = sysmon.compute_stats(self._mon_prev, cur)
            self._mon_prev = cur
            # None 短暫沿用上次有效值以 bridge 偶發缺樣；但持久缺樣即降級為 '--'（不顯示假遙測）。
            stats = sysmon.merge_stale(stats, self._last_stats, self._stale)
            stat_lines = sysmon.format_stat_lines(stats, bar_width=self._monitor_bar_width())
        except Exception:
            stat_lines = []
        composed = self._compose_banner_stats(banner_lines, stat_lines)
        try:
            from rich.text import Text

            return Text.from_ansi(composed)
        except Exception:
            return composed

    def _monitor_bar_width(self) -> int:
        """依 banner pane 寬度算橫條可用寬，讓 bar 撐到 pane 右緣（htop 風）。取不到寬度退回 80。"""
        width = 0
        try:  # 優先用 brand-banner widget 自身寬度（= pane 內容寬）
            width = int(self.query_one("#brand-banner").size.width)
        except Exception:
            pass
        if width <= 0:
            try:
                width = int(self.size.width)
            except Exception:
                width = 0
        if width <= 0:
            width = 80
        # 每監控列固定開銷：label(3)+space+"["+"]"+space+percent(4) = 11；再扣 banner 欄+間距。
        return max(4, min(200, width - self._MON_COL - self._MON_GAP - 11))

    def _compose_banner_stats(self, banner_lines, stat_lines):
        """把 banner 各列補到固定可見寬後，於右側接上監控列（依可見寬對齊）。"""
        out = []
        for i, bline in enumerate(banner_lines):
            visible = branding.strip_ansi(bline)
            row = bline + " " * max(0, self._MON_COL - len(visible))
            if i < len(stat_lines):
                row += " " * self._MON_GAP + stat_lines[i]
            out.append(row)
        return "\n".join(out) + "\n"

    def on_list_view_highlighted(self, event: object) -> None:
        try:
            list_view = self.query_one("#work-list", ListView)
            highlighted_index = getattr(list_view, "index", None)
        except Exception:
            return
        if not isinstance(highlighted_index, int):
            return
        candidate_index = highlighted_index - (1 if self.state.active_pane is not None else 0)
        if candidate_index < 0:
            if self.state.active_pane is not None and self.state.candidate_section:
                try:
                    list_view.index = self._selected_list_index()
                except Exception:
                    pass
            return
        if self.state.selected_pane is not None and candidate_index == self.state.selected_index:
            return
        self.state = self.state.set_selection(candidate_index)
        self._refresh_widgets()

    def _on_refresh_tick(self) -> None:
        self._reconcile_state(light=True)

    def action_move_up(self) -> None:
        self.state = self.state.move_selection(-1)
        self._refresh_widgets()

    def action_move_down(self) -> None:
        self.state = self.state.move_selection(1)
        self._refresh_widgets()

    def _help_modal_open(self) -> bool:
        try:
            return isinstance(self.screen, HelpModal)
        except Exception:
            return False

    def _selected_list_index(self) -> int:
        selected_offset = 1 if self.state.active_pane is not None else 0
        selected = self.state.selected_pane
        if selected is not None:
            for index, pane in enumerate(self.state.candidate_section):
                if pane.pane_id == selected.pane_id:
                    return selected_offset + index
        return selected_offset

    def action_swap_selected(self) -> None:
        if self._help_modal_open():
            return
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
        if self._help_modal_open():
            return
        self.actions.return_to_cockpit(self.state.cockpit_pane_id)

    def _on_help_closed(self, _result: object | None = None) -> None:
        self._reconcile_state(light=True)

    def action_show_help(self) -> None:
        if self._help_modal_open():
            return
        self.push_screen(HelpModal(self.BINDINGS))

    def action_quit_app(self) -> None:
        if self._help_modal_open():
            return
        try:
            self.exit()
        except AttributeError:
            pass

    def on_key(self, event: object) -> None:
        if self._help_modal_open():
            return
        try:
            if hasattr(event, "key"):
                key = event.key
            elif hasattr(event, "character"):
                key = event.character
            else:
                return
        except AttributeError:
            return
        if key in {"enter", "\r"}:
            self.action_swap_selected()

    def _reconcile_state(self, *, light: bool = False) -> None:
        if self.pane_loader is None:
            return
        # The periodic (light) reload skips per-pane preview captures (the detail
        # view captures the selected pane's preview on demand instead). A tick is
        # then one `list-panes` plus a tiny `ps` per title-less minicom pane — no
        # large or per-pane preview reads. Only pass capture_previews when the
        # loader actually accepts it, so we never mask a real TypeError from it.
        kwargs: dict[str, object] = {"cockpit_pane_id": self.state.cockpit_pane_id}
        if light and self._loader_accepts_capture_previews():
            kwargs["capture_previews"] = False
        panes = self.pane_loader(**kwargs)
        self.state = self.state.refresh(panes)
        try:
            self._refresh_widgets()
        except Exception:
            pass

    def _loader_accepts_capture_previews(self) -> bool:
        try:
            params = inspect.signature(self.pane_loader).parameters
        except (TypeError, ValueError):
            return False
        return "capture_previews" in params or any(
            param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
        )

    def _selected_preview(self, pane: PaneRecord) -> tuple[str, ...]:
        if self.preview_loader is not None and pane.pane_id != self.state.cockpit_pane_id:
            try:
                return self.preview_loader(pane.pane_id)
            except Exception:
                return pane.preview
        return pane.preview

    def _work_list_items(self, active: PaneRecord | None) -> tuple[str, ...]:
        items: list[str] = []
        if active is not None:
            items.append(f"[ACTIVE] {pane_display_label(active)}")
        selected = self.state.selected_pane
        for pane in self.state.candidate_section:
            prefix = ">" if selected and pane.pane_id == selected.pane_id else " "
            items.append(f"{prefix} {pane_display_label(pane)}")
        return tuple(items)

    def _refresh_widgets(self) -> None:
        active = self.state.active_pane
        active_text = (
            "<missing>"
            if active is None
            else f"ACTIVE {pane_display_label(active)} {active.command}"
        )
        self.query_one("#active-slot", Static).update(active_text)

        # Only rebuild the work list when its content (labels + selection marker)
        # actually changed, so an idle periodic refresh doesn't visibly flicker
        # the list. The detail/preview below still updates every refresh.
        items = self._work_list_items(active)
        if items != self._last_work_items:
            self._last_work_items = items
            work_list = self.query_one("#work-list", ListView)
            work_list.clear()
            for line in items:
                work_list.append(ListItem(Static(line)))
            try:
                work_list.index = self._selected_list_index()
            except Exception:
                pass

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

        # 破蝦哥 banner + 右側系統監控（每 tick live 刷新）。fail-soft：任何錯誤都不擋刷新。
        try:
            self.query_one("#brand-banner", Static).update(self._brand_banner_renderable())
        except Exception:
            pass
