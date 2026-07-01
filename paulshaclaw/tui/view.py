"""Stage 1 pane→task 概覽表（純文字，供 daemon / CLI / log / Telegram 呈現）。

與 cockpit 共用語意（狀態 glyph + run-green/failed-red 色系，取自 ui-ux-pro-max
design-system），但刻意不 import cockpit（Stage 11）以維持 stage 獨立性：下游失效不連累上游。

**能力分軸（Codex adversarial review #168）**：``color``（ANSI）與 ``unicode``（box-drawing +
狀態 glyph）為兩條獨立軸，各自 fail-safe 自動偵測輸出串流——

* ``color``：``None`` → 只有「非 NO_COLOR 且輸出為互動 TTY」才上色；顯式 bool 覆寫。
* ``unicode``：``None`` → 只有「輸出為 TTY 且其編碼能表示 glyph」才用框線/glyph；否則退回純 ASCII
  （``+ - |`` 邊框、狀態只顯示字詞），避免 ``LC_ALL=C`` / 非 UTF-8 sink 拋 ``UnicodeEncodeError``
  或把控制序列洩進 log。顯式 ``unicode=True`` 由呼叫端自負能力。

純函式、fail-soft、尊重 ``NO_COLOR``；預設對非互動/非 UTF-8 消費者安全。
"""
from __future__ import annotations

import os
import sys

from paulshaclaw.core.config import AppConfig

# 語意色（ANSI 256）——escape 位元組本身皆 ASCII，於 C locale 亦可安全編碼
_GREEN = "\033[38;5;46m"
_RED = "\033[38;5;196m"
_AMBER = "\033[38;5;226m"
_DIM = "\033[38;5;245m"
_LBL = "\033[1;38;5;250m"
_BORDER = "\033[38;5;240m"
_X = "\033[0m"

# 狀態 → (unicode glyph, 色)
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

# unicode 能力探測用樣本（含所有框線與 glyph）
_UNICODE_SAMPLE = "╭┬╮├┼┤╰┴╯─│●✓✗◼◔•"

# unicode / ascii 兩套邊框字元：(TL,TM,TR, ML,MM,MR, BL,BM,BR, H, V)
_BOX_UNICODE = ("╭", "┬", "╮", "├", "┼", "┤", "╰", "┴", "╯", "─", "│")
_BOX_ASCII = ("+", "+", "+", "+", "+", "+", "+", "+", "+", "-", "|")


def _status_glyph(status: str) -> tuple[str, str]:
    return _STATUS.get(status.strip().lower(), _STATUS_DEFAULT)


def _isatty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _can_encode(stream) -> bool:
    enc = getattr(stream, "encoding", None) or "ascii"
    try:
        _UNICODE_SAMPLE.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _resolve_color(color: bool | None, stream) -> bool:
    if color is not None:
        return color
    return (not os.environ.get("NO_COLOR")) and _isatty(stream)


def _resolve_unicode(unicode: bool | None, stream) -> bool:
    if unicode is not None:
        return unicode
    return _isatty(stream) and _can_encode(stream)


def render_pane_task_view(
    config: AppConfig,
    *,
    color: bool | None = None,
    unicode: bool | None = None,
    stream=None,
) -> str:
    """把 pane 指派渲染成對齊表格。

    ``color`` / ``unicode`` 為 ``None`` 時各自依 ``stream``（預設 ``sys.stdout``）自動偵測，
    對非 TTY / 非 UTF-8 sink 預設退回純 ASCII、不上色。顯式 bool 覆寫自動偵測。
    """
    if stream is None:
        stream = sys.stdout
    use_color = _resolve_color(color, stream)
    use_unicode = _resolve_unicode(unicode, stream)
    tl, tm, tr, ml, mm, mr, bl, bm, br, h, v = (
        _BOX_UNICODE if use_unicode else _BOX_ASCII
    )

    # 每列四欄純文字（算寬 + fallback）+ 狀態欄著色版本
    rows: list[tuple[list[str], str]] = []
    for a in config.pane_assignments:
        glyph, hue = _status_glyph(a.status)
        # unicode 模式：glyph + 字詞；ASCII 模式：僅字詞（glyph 為裝飾，去之保 ASCII 安全）
        status_plain = f"{glyph} {a.status}" if use_unicode else a.status
        status_disp = f"{hue}{status_plain}{_X}" if use_color else status_plain
        rows.append(([a.pane_id, a.title, a.task_id, status_plain], status_disp))

    widths = [len(hdr) for hdr in _HEADERS]
    for plain_cells, _ in rows:
        for i, cell in enumerate(plain_cells):
            widths[i] = max(widths[i], len(cell))

    def rule(left: str, mid: str, right: str) -> str:
        bar = mid.join(h * (w + 2) for w in widths)
        return _paint(f"{left}{bar}{right}", _BORDER, use_color)

    sep = _paint(v, _BORDER, use_color)

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
        return sep + sep.join(cells) + sep

    header_cells = [
        f" {_paint(hdr, _LBL, use_color)}{' ' * (widths[i] - len(hdr))} "
        for i, hdr in enumerate(_HEADERS)
    ]
    header = sep + sep.join(header_cells) + sep

    lines = [rule(tl, tm, tr), header, rule(ml, mm, mr)]
    for plain_cells, status_disp in rows:
        lines.append(data_row(plain_cells, status_disp))
    lines.append(rule(bl, bm, br))
    return "\n".join(lines)


def _paint(text: str, hue: str, color: bool) -> str:
    return f"{hue}{text}{_X}" if color else text
