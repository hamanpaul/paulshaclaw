"""Stage 1 pane→task 概覽表（純文字，供 daemon / CLI 呈現）。

與 cockpit 共用同一套語意（狀態 glyph + run-green/failed-red 色系，取自 ui-ux-pro-max
design-system），但刻意不 import cockpit（Stage 11）以維持 stage 獨立性：下游失效不連累上游。
純函式、fail-soft、尊重 ``NO_COLOR``。
"""
from __future__ import annotations

import os

from paulshaclaw.core.config import AppConfig

# 語意色（ANSI 256）：與 cockpit 對齊
_GREEN = "\033[38;5;46m"
_RED = "\033[38;5;196m"
_AMBER = "\033[38;5;226m"
_DIM = "\033[38;5;245m"
_LBL = "\033[1;38;5;250m"
_BORDER = "\033[38;5;240m"
_X = "\033[0m"

# 狀態 → (glyph, 色)
_STATUS = {
    "running": ("●", _GREEN),
    "active": ("●", _GREEN),
    "success": ("✓", _GREEN),
    "passed": ("✓", _GREEN),
    "ok": ("✓", _GREEN),
    "done": ("✓", _DIM),
    "completed": ("✓", _DIM),
    "failed": ("✗", _RED),
    "error": ("✗", _RED),
    "blocked": ("◼", _AMBER),
    "pending": ("◔", _AMBER),
}
_STATUS_DEFAULT = ("•", _DIM)

_HEADERS = ("PANE", "TITLE", "TASK", "STATUS")


def _color_enabled() -> bool:
    return not os.environ.get("NO_COLOR")


def _status_glyph(status: str) -> tuple[str, str]:
    return _STATUS.get(status.strip().lower(), _STATUS_DEFAULT)


def render_pane_task_view(config: AppConfig, *, color: bool | None = None) -> str:
    """把 pane 指派渲染成邊框對齊表；``color`` 預設依 ``NO_COLOR`` env。"""
    use_color = _color_enabled() if color is None else color

    # 每列的純文字四欄（用於算寬與 fallback）+ 狀態欄的著色版本
    rows: list[tuple[list[str], str]] = []
    for a in config.pane_assignments:
        glyph, hue = _status_glyph(a.status)
        status_plain = f"{glyph} {a.status}"
        status_disp = f"{hue}{status_plain}{_X}" if use_color else status_plain
        rows.append(([a.pane_id, a.title, a.task_id, status_plain], status_disp))

    # 欄寬 = max(表頭, 各列純文字)
    widths = [len(h) for h in _HEADERS]
    for plain_cells, _ in rows:
        for i, cell in enumerate(plain_cells):
            widths[i] = max(widths[i], len(cell))

    def rule(left: str, mid: str, right: str) -> str:
        bar = mid.join("─" * (w + 2) for w in widths)
        return _paint(f"{left}{bar}{right}", _BORDER, use_color)

    def data_row(plain_cells: list[str], status_disp: str) -> str:
        cells = []
        for i, cell in enumerate(plain_cells):
            pad = " " * (widths[i] - len(cell))
            if i == 0:
                disp = _paint(cell, _LBL, use_color)  # pane id 稍亮
            elif i == 3:
                disp = status_disp  # 已著色/純文字；用純文字長度補齊
            else:
                disp = cell
            cells.append(f" {disp}{pad} ")
        sep = _paint("│", _BORDER, use_color)
        return sep + sep.join(cells) + sep

    header_cells = [f" {_paint(h, _LBL, use_color)}{' ' * (widths[i] - len(h))} " for i, h in enumerate(_HEADERS)]
    sep = _paint("│", _BORDER, use_color)
    header = sep + sep.join(header_cells) + sep

    lines = [rule("╭", "┬", "╮"), header, rule("├", "┼", "┤")]
    for plain_cells, status_disp in rows:
        lines.append(data_row(plain_cells, status_disp))
    lines.append(rule("╰", "┴", "╯"))
    return "\n".join(lines)


def _paint(text: str, hue: str, color: bool) -> str:
    return f"{hue}{text}{_X}" if color else text
