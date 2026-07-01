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


# 語意狀態樣式（ui-ux-pro-max design-system 色盤）：狀態 → (glyph, rich 顏色)。
# running/success 綠、failed/error 紅、blocked/pending 琥珀、done 收斂為淡灰（去強調），
# 未知狀態退回中性點。純函式，供工作清單／DETAIL／JOBS 上色與單測共用。
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    "running": ("●", "#22C55E"),
    "active": ("●", "#22C55E"),
    "success": ("✓", "#22C55E"),
    "passed": ("✓", "#22C55E"),
    "ok": ("✓", "#22C55E"),
    "done": ("✓", "#64748B"),
    "completed": ("✓", "#64748B"),
    "failed": ("✗", "#EF4444"),
    "error": ("✗", "#EF4444"),
    "blocked": ("◼", "#FBBF24"),
    "pending": ("◔", "#FBBF24"),
    "queued": ("◔", "#94A3B8"),
    "unmapped": ("·", "#64748B"),
}
_STATUS_DEFAULT: tuple[str, str] = ("•", "#94A3B8")


def status_style(status: str) -> tuple[str, str]:
    """狀態字串 → (glyph, rich 顏色)。大小寫不敏感；未知狀態退回中性點。"""
    return _STATUS_STYLE.get((status or "").strip().lower(), _STATUS_DEFAULT)


def format_session_summary(state: CockpitState) -> str:
    """banner 副標：``main · 12 panes · 3 sess``（cockpit pane 不計入 panes 數）。"""
    others = [pane for pane in state.panes if pane.pane_id != state.cockpit_pane_id]
    sessions = {pane.session_name for pane in state.panes}
    return f"{state.cockpit_session_name} · {len(others)} panes · {len(sessions)} sess"


# How often the cockpit re-reads the tmux pane list so the work summary stays
# live. Kept at 30s so the periodic redraw isn't a visible flicker; each tick is
# bounded anyway (one `list-panes`, a tiny `ps` only for title-less minicom
# panes, and one preview capture for the selected pane) — no large or growing
# reads, so it can't pile up the way an unbounded scan would.
REFRESH_INTERVAL_SECONDS = 30.0

# htop 風系統監控要「即時但不吃資源」：把「高頻 /proc 監控」與「低頻 tmux pane 重載」拆成兩個 tick。
# 這條只讀 /proc（CPU/Mem/Swp/I/O/Net）＋就地更新 banner 一個 widget——不 fork tmux、不重建清單，
# 故能用 htop 的 ~1.5s 步調而幾乎不佔資源；就地 update + 固定寬橫條 → Textual 只重繪變動的 cell，不閃。
SYSMON_INTERVAL_SECONDS = 1.5


class CockpitApp(App[None]):
    TITLE = "PaulShiaBro Stage 11 Cockpit"
    # 視覺設計系統（OLED slate + run-green）：與模組同層的 cockpit.tcss。
    # textual 未安裝時只是個字串類別屬性，不影響 import；安裝時才載入套用。
    CSS_PATH = "cockpit.tcss"
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
        with Horizontal(id="main-row"):
            with Vertical(id="left-pane"):
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
        # 兩段式節奏（htop 風）：慢 tick 重載 tmux pane 清單（fork 較重、panes 不常變）；
        # 快 tick 只讀 /proc 就地刷新系統監控（極輕、不閃）。textual stub 無 set_interval，僅容忍其缺席。
        try:
            self.set_interval(REFRESH_INTERVAL_SECONDS, self._on_refresh_tick)
            self.set_interval(SYSMON_INTERVAL_SECONDS, self._on_sysmon_tick)
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

    def _on_sysmon_tick(self) -> None:
        """高頻（htop 步調）系統監控刷新：只讀 /proc 就地更新 banner，不碰 tmux、不重建清單，
        故極輕；就地 update + 固定寬橫條 → 只重繪變動 cell，不閃。"""
        self._refresh_banner()

    def _refresh_banner(self) -> None:
        """就地更新破蝦哥 banner + htop 風系統監控。供 widget 全刷與高頻 sysmon tick 共用。
        fail-soft：任何 /proc 讀取或呈現錯誤都不擋刷新。"""
        try:
            banner = self.query_one("#brand-banner", Static)
            self._set_border(banner, "🦞 破蝦哥 · Cockpit", format_session_summary(self.state))
            banner.update(self._brand_banner_renderable())
        except Exception:
            pass

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

    def _text(self, segments: list[tuple[str, str]]):
        """把 (文字, rich 樣式) 片段組成 rich Text；rich 缺席（textual stub 環境）則退回純字串。

        以 append 逐段上色而非 console markup，避免 pane 標題含 ``[node]`` / ``[▪]`` 之類方括號
        被當成 markup tag 誤解析（fail-soft：任何錯誤都退回純文字，絕不擋刷新）。
        """
        plain = "".join(text for text, _ in segments)
        try:
            from rich.text import Text

            out = Text()
            for text, style in segments:
                out.append(text, style=style or "")
            return out
        except Exception:
            return plain

    def _pane_status(self, pane: PaneRecord) -> tuple[str, str, str]:
        """(glyph, 顏色, 狀態字) — 取該 pane 首個 job 狀態；無 job 回空字（不顯示尾綴）。"""
        jobs = self.jobs_by_pane.get(pane.pane_id, ())
        if not jobs:
            return ("", "#94A3B8", "")
        status = jobs[0].status or ""
        glyph, color = status_style(status)
        return (glyph, color, status)

    def _work_row_segments(self, active: PaneRecord | None) -> list[list[tuple[str, str]]]:
        """工作清單每列的上色片段（順序＝顯示順序）；純字串 key 與彩色 renderable 皆由此衍生，
        確保去閃爍比對（key）與實際上色（Text）永遠一致。"""
        rows: list[list[tuple[str, str]]] = []
        if active is not None:
            rows.append(
                [
                    ("● ", "bold #22C55E"),
                    (f"ACTIVE  {pane_display_label(active)}", "bold #22C55E"),
                ]
            )
        selected = self.state.selected_pane
        for pane in self.state.candidate_section:
            is_selected = bool(selected and pane.pane_id == selected.pane_id)
            marker = "›" if is_selected else " "
            glyph, color, name = self._pane_status(pane)
            segs: list[tuple[str, str]] = [
                (f"{marker} ", "bold #22C55E" if is_selected else "#475569"),
                (pane_display_label(pane), "bold #F8FAFC" if is_selected else "#CBD5E1"),
            ]
            if name:
                segs.append((f"  {glyph} {name}", color))
            rows.append(segs)
        return rows

    def _work_list_items(self, active: PaneRecord | None) -> tuple[str, ...]:
        # 純文字投影：作為去閃爍比對 key，同時是 rich 缺席時的 fallback 呈現。
        return tuple(
            "".join(text for text, _ in segs) for segs in self._work_row_segments(active)
        )

    def _work_list_renderables(self, active: PaneRecord | None) -> list:
        return [self._text(segs) for segs in self._work_row_segments(active)]

    def _refresh_widgets(self) -> None:
        # ACTIVE pane 不再另設狀態條——它就是 WORK 清單首列（綠色 ● ACTIVE）；
        # 「無 active」的降級訊號改由 WORK 面板副標的琥珀 ⚠ 呈現，不再重複一條 bar。
        active = self.state.active_pane

        # Only rebuild the work list when its content (labels + selection marker
        # + per-pane status) actually changed, so an idle periodic refresh doesn't
        # visibly flicker the list. The detail/preview below still updates every
        # refresh. The plain-string key mirrors the coloured Text row-for-row.
        items = self._work_list_items(active)
        if items != self._last_work_items:
            self._last_work_items = items
            work_list = self.query_one("#work-list", ListView)
            work_list.clear()
            for renderable in self._work_list_renderables(active):
                work_list.append(ListItem(Static(renderable)))
            try:
                work_list.index = self._selected_list_index()
            except Exception:
                pass
            subtitle = (
                f"⚠ {self.state.degraded_reason}"
                if self.state.degraded_reason
                else f"{len(self.state.candidate_section)} panes"
            )
            self._set_border(work_list, "WORK · panes", subtitle)

        selected = self.state.selected_pane
        detail_widget = self.query_one("#pane-detail", Static)
        if selected is None:
            self._set_border(detail_widget, "DETAIL", None)
            detail_renderable = self._text(
                [
                    ("No candidate panes\n", "#94A3B8"),
                    *self._state_segment(),
                ]
            )
        else:
            self._set_border(
                detail_widget, f"DETAIL · {selected.pane_id}", selected.display_summary
            )
            segs: list[tuple[str, str]] = [
                (f"{selected.pane_id} ", "bold #F8FAFC"),
                (selected.display_summary, "#F8FAFC"),
                (
                    f"  {selected.command} · {selected.session_name}:"
                    f"{selected.window_index} · {selected.width}×{selected.height}\n",
                    "#64748B",
                ),
            ]
            for line in self._selected_preview(selected):
                segs.append((f"{line}\n", "#94A3B8"))
            jobs = self.jobs_by_pane.get(selected.pane_id, ())
            if jobs:
                for job in jobs:
                    glyph, color = status_style(job.status)
                    segs.append(
                        (f"{glyph} {job.source}:{job.status} {job.trace_id or '-'}\n", color)
                    )
            else:
                segs.append(("· job-state: unmapped\n", "#64748B"))
            segs.extend(self._state_segment())
            detail_renderable = self._text(segs)
        detail_widget.update(detail_renderable)

        all_jobs = [job for jobs in self.jobs_by_pane.values() for job in jobs]
        jobs_widget = self.query_one("#global-jobs", Static)
        if all_jobs:
            self._set_border(jobs_widget, "JOBS", f"{len(all_jobs)} total")
            job_segs: list[tuple[str, str]] = []
            for job in all_jobs[:10]:
                glyph, color = status_style(job.status)
                job_segs.append((f"{job.pane_id or '-':>4} ", "#94A3B8"))
                job_segs.append((f"{glyph} {job.status:<8} ", color))
                job_segs.append((f"{job.trace_id or '-'}\n", "#64748B"))
            jobs_renderable = self._text(job_segs)
        else:
            self._set_border(jobs_widget, "JOBS", "0 total")
            jobs_renderable = self._text([("jobs loaded: 0", "#64748B")])
        jobs_widget.update(jobs_renderable)

        # 破蝦哥 banner + 系統監控：抽成 _refresh_banner，供 widget 全刷與高頻 sysmon tick 共用。
        self._refresh_banner()

    def _state_segment(self) -> list[tuple[str, str]]:
        """DETAIL 底部 ``state:`` 行片段：ok 綠、降級琥珀。"""
        reason = self.state.degraded_reason
        return [(f"state: {reason or 'ok'}", "bold #FBBF24" if reason else "#22C55E")]

    @staticmethod
    def _set_border(widget: object, title: str, subtitle: str | None) -> None:
        """設面板邊框標題／副標；``subtitle=None``（或空字串）明確清空副標——避免殘留上一狀態
        的舊摘要（如 DETAIL 由選取態切回無候選態時副標仍顯示前一個 pane；Copilot review PR #168）。
        stub 或未掛載時 fail-soft。"""
        try:
            widget.border_title = title
            widget.border_subtitle = subtitle or ""
        except Exception:
            pass
