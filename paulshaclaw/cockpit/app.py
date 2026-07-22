from __future__ import annotations

import threading
import time
from collections.abc import Callable

import paulsha_cortex.control.client as control_client
from . import branding, cost_bar, sysmon

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import Footer, Header, ListItem, ListView, Static
except Exception:  # pragma: no cover - fallback when textual not installed
    # Minimal stubs so module is importable without textual installed.
    from typing import Any, Generic, Iterable, TypeVar

    T = TypeVar("T")

    class App(Generic[T]):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.screen = None

        def set_interval(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - noop
            return None

        def query_one(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - noop
            raise LookupError("query_one unavailable in textual fallback")

        def push_screen(self, screen: Any) -> None:  # pragma: no cover - noop
            self.screen = screen

        def exit(self) -> None:  # pragma: no cover - noop
            return None

    ComposeResult = Iterable[Any]

    class Binding:  # pragma: no cover - noop
        def __init__(self, key: str, handler: str, description: str) -> None:
            self.key = key
            self.handler = handler
            self.description = description

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
from .manager_panel import ManagerModal
from .models import JobRow, JobSummary, PaneRecord
from .store import CockpitState


class WorkItem(ListItem):
    """工作清單列：附掛 pane_id 供雙擊偵測直讀（Selected.item.pane_id）。"""

    def __init__(self, *args, pane_id: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pane_id = pane_id


class WorkListView(ListView):
    """WORK 清單：enter 覆寫為直達 app swap action。"""

    def action_select_cursor(self) -> None:
        app = getattr(self, "app", None)
        action = getattr(app, "action_swap_selected", None)
        if callable(action):
            action()


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
    "attention": ("!", "#FBBF24"),
    "blocked": ("◼", "#FBBF24"),
    "pending": ("◔", "#FBBF24"),
    "ready": ("◔", "#94A3B8"),
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


def format_work_pane_subtitle(state: CockpitState) -> str:
    here = state.cockpit_session_name
    if state.cockpit_window_index is not None:
        here = f"{here}:{state.cockpit_window_index}"
    suffix = (
        f"⚠ {state.degraded_reason}"
        if state.degraded_reason
        else f"{len(state.candidate_section)} panes"
    )
    return f"{here} · {suffix}"


def _slice_id_from_item(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("slice_id", "id", "name", "title"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def slices_from_status(status: dict[str, object]) -> tuple[JobRow, ...]:
    if not isinstance(status, dict) or status.get("degraded"):
        return ()

    rows: list[JobRow] = []

    in_flight = status.get("in_flight")
    if isinstance(in_flight, list):
        for item in in_flight:
            if not isinstance(item, dict):
                continue
            slice_id = _slice_id_from_item(item)
            if not slice_id:
                continue
            state = str(item.get("state") or "running")
            rows.append(JobRow(slice_id=slice_id, state=state, source_section="in_flight"))

    ready = status.get("ready")
    if isinstance(ready, list):
        for item in ready:
            slice_id = _slice_id_from_item(item)
            if not slice_id:
                continue
            state = str(item.get("state")) if isinstance(item, dict) and item.get("state") else "ready"
            rows.append(JobRow(slice_id=slice_id, state=state, source_section="ready"))

    held = status.get("held")
    if isinstance(held, list):
        for item in held:
            if not isinstance(item, dict):
                continue
            slice_id = _slice_id_from_item(item)
            if not slice_id:
                continue
            rows.append(JobRow(slice_id=slice_id, state="blocked", source_section="held"))

    attention = status.get("attention")
    if isinstance(attention, list):
        for item in attention:
            if not isinstance(item, dict):
                continue
            slice_id = _slice_id_from_item(item)
            if not slice_id:
                continue
            state = str(item.get("job_state") or item.get("gate_state") or "attention")
            rows.append(JobRow(slice_id=slice_id, state=state, source_section="attention"))

    recent_done = status.get("recent_done")
    if isinstance(recent_done, list):
        for item in recent_done:
            if not isinstance(item, dict):
                continue
            slice_id = _slice_id_from_item(item)
            if not slice_id:
                continue
            state = str(item.get("gate_status") or item.get("state") or "done")
            rows.append(JobRow(slice_id=slice_id, state=state, source_section="recent_done"))

    return tuple(rows)


# How often the cockpit re-reads the tmux pane list so the work summary stays
# live. Kept at 30s so the periodic redraw isn't a visible flicker; each tick is
# bounded anyway (one `list-panes`, a tiny `ps` only for title-less minicom
# panes) — no large or growing
# reads, so it can't pile up the way an unbounded scan would.
REFRESH_INTERVAL_SECONDS = 30.0
DOUBLE_CLICK_SECONDS = 0.4

# htop 風系統監控要「即時但不吃資源」：把「高頻 /proc 監控」與「低頻 tmux pane 重載」拆成兩個 tick。
# 這條只讀 /proc（CPU/Mem/Swp/I/O/Net）＋就地更新 banner 一個 widget——不 fork tmux、不重建清單，
# 故能用 htop 的 ~1.5s 步調而幾乎不佔資源；就地 update + 固定寬橫條 → Textual 只重繪變動的 cell，不閃。
SYSMON_INTERVAL_SECONDS = 1.5

# cost footer 版面切換門檻：banner 寬 >= 此值 → 單行延伸滿 banner 寬；否則 cdx 併 Net 行、
# cc+cpt 另成一列（單行 cost 約 61 字，故需 >= 62 才塞得下整條）。
_COST_SINGLE_LINE_MIN_WIDTH = 62


class CockpitApp(App[None]):
    TITLE = "PaulShiaBro Cockpit"
    # 視覺設計系統（OLED slate + run-green）：與模組同層的 cockpit.tcss。
    # textual 未安裝時只是個字串類別屬性，不影響 import；安裝時才載入套用。
    CSS_PATH = "cockpit.tcss"
    BINDINGS = [
        Binding("up", "move_up", "↑/↓ 選擇"),
        Binding("down", "move_down", "↑/↓ 選擇"),
        Binding("enter", "swap_selected", "Enter 把選中的 pane 換到我面前"),
        Binding("c", "focus_cockpit", "c 回 cockpit"),
        Binding("m", "manager_panel", "m 顯示 manager 面板"),
        Binding("q", "quit_app", "q 離開 cockpit"),
        Binding("t", "manager_tick", "t 送出 manager tick"),
        Binding("j", "toggle_jobs", "j 收合/展開 JOBS"),
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
        clock: Callable[[], float] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.jobs_by_pane = jobs_by_pane
        self.actions = actions
        self.pane_loader = pane_loader
        self._clock: Callable[[], float] = clock or time.monotonic
        self._last_click: tuple[str, float] | None = None
        self._displacement: tuple[str, str] | None = None
        self._jobs_collapsed = False
        # 系統監控（banner 右側 htop 風）：CPU%/IO%/Net 速率需前後快照差值，故保留上次快照；
        # _last_stats 存最後有效讀數，None 時沿用以避免快速重刷閃爍。
        self._mon_prev = None
        self._last_stats: dict = {}   # 最後有效讀數（bridge 偶發缺樣）
        self._stale: dict = {}        # 各項連續缺樣次數（超過容忍即降級為 '--'）
        # Last-rendered work-list content, so we skip rebuilding (and flickering)
        # the list on refreshes that didn't change it.
        self._last_work_items: tuple[str, ...] | None = None
        self.manager_client = control_client
        self.thread_factory = threading.Thread

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
        clock: Callable[[], float] | None = None,
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
            clock=clock,
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="brand-banner")  # 破蝦哥 🦞 banner（issue #116）；內容於 on_mount 填入
        yield WorkListView(id="work-list")
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
        # cost footer（Stage 8）自適應版面（唯讀 cache、fail-soft）：
        #   banner 寬 >= 62 → 單行延伸滿整個 banner 寬（放在 banner 底下、不縮排 stat 欄）；
        #   < 62         → cdx 併到 Net 那行、cc+cpt 另成一列（窄版兩行解）。
        full_width_cost: str | None = None
        try:
            full_w = self._banner_raw_width()
            if full_w >= _COST_SINGLE_LINE_MIN_WIDTH:
                line = cost_bar.cost_line(full_w)
                if line:
                    # 向右對齊：前導補白到貼齊 banner 右緣。pad 依當下 full_w 計算，
                    # 故每次 render（含 resize，見 on_resize）都重新靠右。
                    pad = max(0, full_w - len(branding.strip_ansi(line)))
                    full_width_cost = " " * pad + line
            else:
                net_width = len(branding.strip_ansi(stat_lines[-1])) if stat_lines else 0
                net_suffix, cost_rest = cost_bar.cost_split(self._cost_line_width(), net_width)
                if net_suffix and stat_lines:
                    stat_lines[-1] = stat_lines[-1] + net_suffix
                if cost_rest:
                    stat_lines = [*stat_lines, cost_rest]
        except Exception:
            full_width_cost = None
        composed = self._compose_banner_stats(banner_lines, stat_lines)
        # 單行 cost 以整個 banner 寬、向右對齊渲染 → 接在 composed 之後、不受 mascot 欄縮排。
        if full_width_cost:
            composed += full_width_cost + "\n"
        try:
            from rich.text import Text

            return Text.from_ansi(composed)
        except Exception:
            return composed

    def _banner_raw_width(self) -> int:
        """banner pane 的可見寬（brand-banner widget → app → 退回 80）。"""
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
        return width

    def _monitor_bar_width(self) -> int:
        """依 banner pane 寬度算橫條可用寬，讓 bar 撐到 pane 右緣（htop 風）。取不到寬度退回 80。"""
        # 每監控列固定開銷：label(3)+space+"["+"]"+space+percent(4) = 11（百分比在 ] 右側）；
        # 再扣 banner 欄+間距。長條內仍疊 used/total（Mem/Swp）。
        return max(4, min(200, self._banner_raw_width() - self._MON_COL - self._MON_GAP - 11))

    def _cost_line_width(self) -> int:
        """cost footer 可用寬 = banner 寬 - mascot 欄 - 間距（自由格式，無 sysmon 的 11 開銷）。"""
        return max(4, min(240, self._banner_raw_width() - self._MON_COL - self._MON_GAP))

    def _compose_banner_stats(self, banner_lines, stat_lines):
        """把 banner 各列補到固定可見寬後，於右側接上監控列（依可見寬對齊）。

        stat 行數可多於破蝦哥 art 行數（如 sysmon 之後再接 cost footer）；多出來的
        stat 行仍要輸出，左側 mascot 欄留空白對齊。"""
        out = []
        for i in range(max(len(banner_lines), len(stat_lines))):
            if i < len(banner_lines):
                bline = banner_lines[i]
                visible = branding.strip_ansi(bline)
                row = bline + " " * max(0, self._MON_COL - len(visible))
            else:
                row = " " * self._MON_COL
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
        self._reconcile_state()
        self._refresh_jobs_panel()
        self._refresh_manager_panel()

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

    def on_resize(self, event: object) -> None:
        """終端／pane resize 時立即重排 banner——cost 單行右對齊的前導補白需依當下寬度重算，
        不能等下一個 sysmon tick 才更新。fail-soft，不擋 resize。"""
        try:
            self._refresh_banner()
        except Exception:
            pass

    def action_move_up(self) -> None:
        if self._background_actions_blocked():
            return
        self.state = self.state.move_selection(-1)
        self._refresh_widgets()

    def action_move_down(self) -> None:
        if self._background_actions_blocked():
            return
        self.state = self.state.move_selection(1)
        self._refresh_widgets()

    def _help_modal_open(self) -> bool:
        try:
            return isinstance(self.screen, HelpModal)
        except Exception:
            return False

    def _manager_modal_open(self) -> bool:
        try:
            return isinstance(self.screen, ManagerModal)
        except Exception:
            return False

    def _background_actions_blocked(self) -> bool:
        return self._help_modal_open() or self._manager_modal_open()

    def _selected_list_index(self) -> int:
        selected_offset = 1 if self.state.active_pane is not None else 0
        selected = self.state.selected_pane
        if selected is not None:
            for index, pane in enumerate(self.state.candidate_section):
                if pane.pane_id == selected.pane_id:
                    return selected_offset + index
        return selected_offset

    def action_swap_selected(self) -> None:
        self._last_click = None
        if self._background_actions_blocked():
            return
        active_pane = self.state.active_pane
        selected_pane = self.state.selected_pane
        if active_pane is None or selected_pane is None:
            return
        self._activate(selected_pane.pane_id, active_pane.pane_id)

    def action_focus_cockpit(self) -> None:
        if self._background_actions_blocked():
            return
        self.actions.return_to_cockpit(self.state.cockpit_pane_id)

    def _on_help_closed(self, _result: object | None = None) -> None:
        self._reconcile_state()

    def action_show_help(self) -> None:
        if self._background_actions_blocked():
            return
        self._last_click = None
        self.push_screen(HelpModal(self.BINDINGS))

    def action_manager_panel(self) -> None:
        if self._help_modal_open():
            return
        self._last_click = None
        status = self.manager_client.read_status()
        if self._manager_modal_open():
            try:
                self.screen.update_status(status)
            except Exception:
                pass
            return
        self.push_screen(ManagerModal(status))

    def action_manager_tick(self) -> None:
        if self._background_actions_blocked():
            return
        worker = self.thread_factory(target=self._run_manager_tick, daemon=True)
        worker.start()

    def _run_manager_tick(self) -> None:
        error_message: str | None = None
        try:
            self.manager_client.submit_request("tick", {}, "cockpit")
        except Exception as exc:  # noqa: BLE001
            error_message = f"manager tick submit failed: {type(exc).__name__}: {exc}"
        finally:
            callback = getattr(self, "call_from_thread", None)
            if callable(callback):
                callback(lambda: self._after_manager_tick(error_message))
            else:
                self._after_manager_tick(error_message)

    def _after_manager_tick(self, error_message: str | None = None) -> None:
        if error_message:
            notifier = getattr(self, "notify", None)
            if callable(notifier):
                try:
                    notifier(error_message, severity="error")
                except TypeError:
                    notifier(error_message)
        self._refresh_manager_panel()
        self._reconcile_state()

    def _refresh_manager_panel(self) -> None:
        if not self._manager_modal_open():
            return
        try:
            self.screen.update_status(self.manager_client.read_status())
        except Exception:
            pass

    def action_quit_app(self) -> None:
        if self._background_actions_blocked():
            return
        try:
            self.exit()
        except AttributeError:
            pass

    def _reconcile_state(self) -> None:
        if self.pane_loader is None:
            return
        panes = self.pane_loader(cockpit_pane_id=self.state.cockpit_pane_id)
        self.state = self.state.refresh(panes)
        try:
            self._refresh_widgets()
        except Exception:
            pass

    def on_list_view_selected(self, event: object) -> None:
        list_view = getattr(event, "list_view", None)
        if getattr(list_view, "id", None) != "work-list":
            return
        pane_id = getattr(getattr(event, "item", None), "pane_id", None)
        active = self.state.active_pane
        if not pane_id or (active is not None and pane_id == active.pane_id):
            self._last_click = None
            return
        now = self._clock()
        last = self._last_click
        if last is not None and last[0] == pane_id and now - last[1] < DOUBLE_CLICK_SECONDS:
            selected = self.state.selected_pane
            if selected is not None and selected.pane_id == pane_id:
                self.action_swap_selected()
                return
        self._last_click = (pane_id, now)

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

    def _work_row_pane_ids(self, active: PaneRecord | None) -> tuple[str, ...]:
        """與 _work_list_renderables 同順序的 pane_id 投影（ACTIVE 首列）。"""
        ids: list[str] = []
        if active is not None:
            ids.append(active.pane_id)
        ids.extend(pane.pane_id for pane in self.state.candidate_section)
        return tuple(ids)

    def _refresh_widgets(self) -> None:
        # ACTIVE pane 不再另設狀態條——它就是 WORK 清單首列（綠色 ● ACTIVE）；
        # 「無 active」的降級訊號改由 WORK 面板副標的琥珀 ⚠ 呈現，不再重複一條 bar。
        active = self.state.active_pane

        # Only rebuild the work list when its content (labels + selection marker
        # + per-pane status) actually changed, so an idle periodic refresh doesn't
        # visibly flicker the list. The plain-string key mirrors the coloured Text
        # row-for-row.
        items = self._work_list_items(active)
        if items != self._last_work_items:
            self._last_work_items = items
            work_list = self.query_one("#work-list", ListView)
            work_list.clear()
            for renderable, pane_id in zip(
                self._work_list_renderables(active), self._work_row_pane_ids(active)
            ):
                work_list.append(
                    WorkItem(
                        Static(renderable),
                        pane_id=pane_id,
                        id=f"row-{pane_id.lstrip('%')}",
                    )
                )
            try:
                work_list.index = self._selected_list_index()
            except Exception:
                pass
            self._set_border(work_list, "WORK · panes", format_work_pane_subtitle(self.state))

        self._refresh_jobs_panel()

        # 破蝦哥 banner + 系統監控：抽成 _refresh_banner，供 widget 全刷與高頻 sysmon tick 共用。
        self._refresh_banner()

    def _refresh_jobs_panel(self) -> None:
        jobs_widget = self.query_one("#global-jobs", Static)
        status = self.manager_client.read_status()
        if not isinstance(status, dict):
            status = {}
        rows = slices_from_status(status)
        if self._jobs_collapsed:
            self._set_border(jobs_widget, f"JOBS ▸ {len(rows)} slices", None)
            try:
                jobs_widget.styles.max_height = 3
            except Exception:
                pass
            jobs_widget.update("")
            return
        try:
            jobs_widget.styles.max_height = 12
        except Exception:
            pass

        if status.get("degraded"):
            reason = str(status.get("degraded_reason") or "--")
            self._set_border(jobs_widget, "JOBS", "degraded")
            jobs_widget.update(self._text([(f"degraded: {reason}", "#FBBF24")]))
            return

        if rows:
            self._set_border(jobs_widget, "JOBS", f"{len(rows)} slices")
            job_segs: list[tuple[str, str]] = []
            for row in rows[:10]:
                glyph, color = status_style(row.state)
                job_segs.append((f"{row.source_section:>11} ", "#94A3B8"))
                job_segs.append((f"{glyph} {row.state:<9} ", color))
                job_segs.append((f"{row.slice_id}\n", "#CBD5E1"))
            jobs_renderable = self._text(job_segs)
        else:
            self._set_border(jobs_widget, "JOBS", "0 slices")
            jobs_renderable = self._text([("manager slices: 0", "#64748B")])
        jobs_widget.update(jobs_renderable)

    def action_toggle_jobs(self) -> None:
        if self._background_actions_blocked():
            return
        self._jobs_collapsed = not self._jobs_collapsed
        self._refresh_jobs_panel()

    def _activate(self, target_pane_id: str, slot_pane_id: str) -> None:
        proceed = True
        record = self._displacement
        if record is not None:
            occupant_id, displaced_id = record
            alive = {pane.pane_id for pane in self.state.panes}
            if occupant_id in alive and displaced_id in alive:
                try:
                    self.actions.swap_selected_with_active(
                        selected_pane_id=displaced_id,
                        active_pane_id=occupant_id,
                    )
                    self._displacement = None
                    if target_pane_id == displaced_id:
                        proceed = False
                    else:
                        slot_pane_id = displaced_id
                except Exception as exc:  # noqa: BLE001
                    self._displacement = None
                    self._notify_soft(f"restore swap failed: {exc}")
                    proceed = False
            else:
                self._displacement = None
        if proceed:
            try:
                self.actions.swap_selected_with_active(
                    selected_pane_id=target_pane_id,
                    active_pane_id=slot_pane_id,
                )
                self._displacement = (target_pane_id, slot_pane_id)
                self.actions.focus_pane(target_pane_id)
            except Exception as exc:  # noqa: BLE001
                self._notify_soft(f"swap failed: {exc}")
        self._reconcile_state()

    def _notify_soft(self, message: str) -> None:
        notifier = getattr(self, "notify", None)
        if callable(notifier):
            try:
                notifier(message, severity="error")
            except TypeError:
                notifier(message)

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
