"""JOBS 面板：Tree 為底的節點模型與 widget（取代舊 Static + 行預算截斷）。

不 import .app（避免循環）；app.py 反過來從這裡 import 並 re-export，
保持模組層名稱不變以維持既有測試相容。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .models import JobGroup, JobRow

try:
    from textual.widgets import Tree

    _HAS_TEXTUAL = True
except Exception:  # pragma: no cover - fallback when textual not installed
    _HAS_TEXTUAL = False


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
    # 最該亮起來的狀態先前沒有樣式，退回中性灰點——等人工的列看起來跟雜訊一樣。
    "needs_human": ("!", "#FBBF24"),
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


def _display_width(text: str) -> int:
    """終端顯示寬度：CJK 全形字佔兩欄，用 len() 排版會整欄歪掉。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad_display(text: str, width: int) -> str:
    """依顯示寬度補到定寬（`f"{s:<18}"` 會把全形字當一欄，中文欄位對不齊）。"""
    return text + " " * max(0, width - _display_width(text))


def _ellipsize_middle(text: str, width: int) -> str:
    """過長的 slice 名從中間省略：頭（work 名）與尾（phase）都是辨識關鍵，不能只砍一端。"""
    if _display_width(text) <= width or width < 3:
        return text
    head: list[str] = []
    tail: list[str] = []
    used = 1  # 省略號本身
    chars = list(text)
    while chars:
        ch = chars.pop(0) if len(head) <= len(tail) else chars.pop()
        cost = _display_width(ch)
        if used + cost > width:
            break
        used += cost
        (head if len(head) <= len(tail) else tail).append(ch)
    return "".join(head) + "…" + "".join(reversed(tail))


def _fit_trailer(parts: tuple[str, ...], width: int) -> str:
    """次要欄依重要性由高到低排；塞不下時從尾端整項丟棄並標示有省略。

    硬切字元會把 `paulsha-cortex` 砍成半個名字，比少顯示一項更難讀。
    """
    kept = [part for part in parts if part]
    dropped = False
    while kept and _display_width(" · ".join(kept)) > width:
        kept.pop()
        dropped = True
    text = " · ".join(kept)
    if dropped and kept:
        text = f"{text} …"
    return text


# JOBS 主行欄寬（顯示寬，非字元數）與量不到 widget 寬度時的保守後備值。
# 超出可用寬度會被 Textual 折行，折出來的那行不在行預算內，實際顯示會比算的少。
_JOBS_STATE_COL = 16
_JOBS_NAME_COL = 26
_JOBS_WIDTH_FALLBACK = 88


@dataclass(frozen=True)
class JobsNodeSpec:
    """build_jobs_nodes 的純資料輸出：一個 Tree 節點該長什麼樣，不碰 widget。"""

    key: str
    segments: tuple[tuple[str, str], ...]
    children: tuple["JobsNodeSpec", ...] = ()
    expand: bool = False


def _group_state_key(group: JobGroup) -> str:
    """多 phase 群組的上色依據：有人在等就照 attention 上色，否則跟著領頭 slice。"""
    return "attention" if group.needs_human else group.lead.state


def _row_state_key(row: JobRow) -> str:
    """單一 slice 的上色依據：needs_human 一律當 attention，不管上游原始 state 字串是什麼。"""
    return "needs_human" if row.needs_human else row.state


def _detail_child(key: str, detail: str) -> JobsNodeSpec:
    # 黃色 ↳ detail：detail_line 含可複製命令，這裡不截斷，超寬交給 Tree 的橫向捲動。
    return JobsNodeSpec(key=key, segments=((f"↳ {detail}", "#FBBF24"),))


def _single_detail_children(group: JobGroup) -> tuple[JobsNodeSpec, ...]:
    if group.needs_human and group.detail_line:
        return (_detail_child(f"{group.key}/detail", group.detail_line),)
    return ()


def _phase_child(group: JobGroup, row: JobRow) -> JobsNodeSpec:
    glyph, color = status_style(_row_state_key(row))
    label_state = row.human_state or row.state
    phase_name = group._phase_label(row)
    segments = (
        (f"{glyph} {_pad_display(label_state, _JOBS_STATE_COL)} ", color),
        (phase_name, "#E2E8F0"),
    )
    children: tuple[JobsNodeSpec, ...] = ()
    if row.needs_human and row.detail_line:
        children = (_detail_child(f"{group.key}/{row.slice_id}/detail", row.detail_line),)
    return JobsNodeSpec(
        key=f"{group.key}/{row.slice_id}",
        segments=segments,
        children=children,
        # 該 phase 自己在等人，就自動展開讓 detail 直接可見，不必再多按一次。
        expand=row.needs_human,
    )


def build_jobs_nodes(
    groups: tuple[JobGroup, ...], width: int = _JOBS_WIDTH_FALLBACK
) -> tuple[JobsNodeSpec, ...]:
    """JobGroup 序列 → Tree 節點描述（純函式，不碰 widget，供單測與 widget 共用）。"""
    specs: list[JobsNodeSpec] = []
    for group in groups:
        glyph, color = status_style(
            group.lead.state if group.is_single else _group_state_key(group)
        )
        trailer = _fit_trailer(
            (
                group.project,
                # branch 帶著 feature/<N>-<slug> 的 issue 編號，是上游 repo 仍為 null
                # （cortex#465）時 workflow job 唯一的歸屬線索；排在 project 之後，
                # _fit_trailer 從尾端丟棄時它比 workflow id 活得久。
                group.branch,
                # 多 phase 群的主欄位已經是 workflow id，不再重複一次。
                group.workflow_id if group.is_single else "",
                group.note,
                group.raw_state,
                group.job_id,
            ),
            width - _JOBS_STATE_COL - _JOBS_NAME_COL - 4,
        )
        main_segments = (
            (f"{glyph} {_pad_display(group.headline_state, _JOBS_STATE_COL)} ", color),
            (
                f"{_pad_display(_ellipsize_middle(group.display_name, _JOBS_NAME_COL), _JOBS_NAME_COL)} ",
                "#E2E8F0",
            ),
            (trailer, "#64748B"),
        )
        if group.is_single:
            children = _single_detail_children(group)
        else:
            children = tuple(_phase_child(group, row) for row in group.rows)
        specs.append(
            JobsNodeSpec(
                key=group.key,
                segments=main_segments,
                children=children,
                expand=group.needs_human,
            )
        )
    return tuple(specs)


def _project_specs(specs: tuple[JobsNodeSpec, ...]) -> tuple[tuple[str, str], ...]:
    """純文字投影（忽略顏色／expand）：去閃爍重建判斷用的 diff key。"""
    flat: list[tuple[str, str]] = []

    def walk(items: tuple[JobsNodeSpec, ...]) -> None:
        for spec in items:
            flat.append((spec.key, "".join(text for text, _ in spec.segments)))
            walk(spec.children)

    walk(specs)
    return tuple(flat)


if _HAS_TEXTUAL:

    def _label(segments: tuple[tuple[str, str], ...]):
        # Tree.process_label 吃 rich Text；textual 本身硬依賴 rich，這裡不必像
        # app.py 的 _text 那樣 fail-soft（此分支已確定在有 textual 的環境）。
        from rich.text import Text

        text = Text()
        for value, style in segments:
            text.append(value, style=style or "")
        return text

    class JobsPanel(Tree):
        """JOBS 面板：全部鍵盤／滑鼠互動走 Tree 原生（enter/space toggle、方向鍵、
        滾輪、點擊箭頭），這裡只管資料 → 節點的重建，以及重建之間要保留的東西：
        使用者手動展開/收合、cursor 所在 node、scroll 位置。
        """

        def __init__(
            self,
            *,
            name: str | None = None,
            id: str | None = None,
            classes: str | None = None,
            disabled: bool = False,
        ) -> None:
            super().__init__("jobs", name=name, id=id, classes=classes, disabled=disabled)
            self.show_root = False
            self.guide_depth = 2
            # key -> 使用者上次手動設的展開狀態；優先於 spec.expand 的預設值。
            self._user_expanded: dict[str, bool] = {}
            self._last_projection: tuple[tuple[str, str], ...] | None = None

        # node.expand()/collapse()（space、enter 觸發 auto_expand、滑鼠點箭頭）
        # 一定會 post 這兩個 message；重建時我們改用 add(expand=...) 直接設
        # _expanded，不會走這條路徑，所以這裡收到的必然是使用者手動動作。
        def on_tree_node_expanded(self, event: "Tree.NodeExpanded") -> None:
            key = event.node.data
            if key is not None:
                self._user_expanded[key] = True

        def on_tree_node_collapsed(self, event: "Tree.NodeCollapsed") -> None:
            key = event.node.data
            if key is not None:
                self._user_expanded[key] = False

        def _panel_width(self) -> int:
            """widget 目前可寫入的顯示寬度；量不到（尚未 layout）時退回保守值。"""
            try:
                width = int(self.size.width) - 2
            except (TypeError, ValueError, AttributeError):
                return _JOBS_WIDTH_FALLBACK
            return width if width > 40 else _JOBS_WIDTH_FALLBACK

        def set_groups(self, groups: tuple[JobGroup, ...]) -> None:
            specs = build_jobs_nodes(tuple(groups), width=self._panel_width())
            projection = _project_specs(specs)
            if projection == self._last_projection:
                return

            cursor_key = self.cursor_node.data if self.cursor_node is not None else None
            scroll_offset = self.scroll_offset
            restored: list[object] = [None]

            def build(parent, spec: JobsNodeSpec) -> None:
                label = _label(spec.segments)
                if spec.children:
                    expand = self._user_expanded.get(spec.key, spec.expand)
                    node = parent.add(label, data=spec.key, expand=expand)
                    for child in spec.children:
                        build(node, child)
                else:
                    node = parent.add_leaf(label, data=spec.key)
                if spec.key == cursor_key:
                    restored[0] = node

            self.clear()
            self._last_projection = projection
            for spec in specs:
                build(self.root, spec)

            # node._line 要等 Tree 真的跑過一次 _build()（render 或存取 _tree_lines
            # 才會觸發）才有正確值；剛 add() 完就呼叫 select_node 會撿到 stale -1，
            # 被 cursor_line 的 validator clamp 成 0，選到錯的列。延到下一次 refresh
            # 之後再選，這時 _tree_lines 已經重建過。
            self.call_after_refresh(self._restore_selection, restored[0], scroll_offset)

        def _restore_selection(self, node, offset) -> None:
            if node is not None:
                self.select_node(node)
            try:
                target_x = min(max(offset.x, 0), self.max_scroll_x)
                target_y = min(max(offset.y, 0), self.max_scroll_y)
            except Exception:
                return
            self.scroll_to(x=target_x, y=target_y, animate=False)

        def clear(self):
            # 外部（收合分支）直呼 clear() 時投影快取必須一併失效，否則展開後
            # 同一份 groups 會被 diff 判「沒變」而跳過重建，Tree 停留在空白。
            self._last_projection = None
            return super().clear()

        def set_message(self, text: str, style: str = "#64748B") -> None:
            """清空並顯示單一 leaf 訊息（degraded／0 slices 用）。"""
            projection = (("__message__", text),)
            if projection == self._last_projection:
                return
            self.clear()
            self._last_projection = projection
            self.root.add_leaf(_label(((text, style),)), data="__message__")

else:  # pragma: no cover - fallback when textual not installed

    class JobsPanel:  # type: ignore[no-redef]
        """textual 缺席時的退化 stub：純 noop，讓 import 不炸。"""

        def __init__(self, *args, **kwargs) -> None:
            self.border_title = ""
            self.border_subtitle = ""

        def set_groups(self, groups) -> None:  # pragma: no cover - noop
            return None

        def set_message(self, text: str, style: str = "#64748B") -> None:  # pragma: no cover - noop
            return None

        def clear(self) -> None:  # pragma: no cover - noop
            return None
