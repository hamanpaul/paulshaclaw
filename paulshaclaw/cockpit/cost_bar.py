"""cockpit banner 的 cost footer 列。

唯讀消費者：讀 Stage 8 cost 已 cache 的 snapshot（由 Claude Code statusLine 每次刷新
時寫入），渲染成 ANSI 前景色（無背景色）的一列，接在 sysmon 之後。**絕不** 呼叫
``build_current_snapshot``（會打網路 chatgpt.com / api.github.com，卡住 TUI）。全程
fail-soft：任何錯誤都回 None，不擋 banner。
"""

from __future__ import annotations

import re

from paulshaclaw.cost.cache import SnapshotCache
from paulshaclaw.cost.config import load_cost_config
from paulshaclaw.cost.formatter import (
    format_cockpit_cdx,
    format_cockpit_footer,
    format_cockpit_rest,
)
from paulshaclaw.cost.models import CostSnapshot

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_ANSI_RESET = "\033[0m"
# footer 分隔符（colour238 dim grey）的 ANSI 前景色版本。
_SEP_ANSI = "\033[38;5;238m|\033[0m"


def _ansi_clip(text: str, width: int) -> str:
    """截斷到 ``width`` 個「可見」字元，保留過程中的 ANSI 碼；有截斷時補 reset。"""
    if width <= 0:
        return ""
    if len(_ANSI_RE.sub("", text)) <= width:
        return text
    out: list[str] = []
    count = 0
    i = 0
    while i < len(text) and count < width:
        match = _ANSI_RE.match(text, i)
        if match:
            out.append(match.group())
            i = match.end()
            continue
        out.append(text[i])
        count += 1
        i += 1
    return "".join(out) + _ANSI_RESET


def read_snapshot() -> CostSnapshot | None:
    """讀已 cache 的 cost snapshot（不重建、不打網路）。任何錯誤回 None。"""
    try:
        config = load_cost_config()
        cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
        return cache.read_stale()
    except Exception:  # noqa: BLE001 - fail-soft，絕不擋 TUI
        return None


def cost_line(width: int) -> str | None:
    """回一列 ANSI 前景色的整條 cost footer（截到 ``width``）；無資料/出錯回 None。"""
    snapshot = read_snapshot()
    if snapshot is None:
        return None
    try:
        line = format_cockpit_footer(snapshot)
    except Exception:  # noqa: BLE001 - fail-soft
        return None
    if not line.strip():
        return None
    return _ansi_clip(line, width)


def cost_split(cost_width: int, net_width: int) -> tuple[str | None, str | None]:
    """窄版面用：回 ``(net_suffix, rest_line)``——cdx 段（含前導 ` | `）併到 Net 行，
    cc+cpt 為下一行。``net_suffix`` 截到 Net 行剩餘寬、``rest_line`` 截到 ``cost_width``。
    無資料/出錯回 ``(None, None)``（fail-soft）。"""
    snapshot = read_snapshot()
    if snapshot is None:
        return (None, None)
    try:
        cdx = format_cockpit_cdx(snapshot)
        rest = format_cockpit_rest(snapshot)
    except Exception:  # noqa: BLE001 - fail-soft
        return (None, None)

    net_suffix: str | None = None
    if cdx.strip():
        budget = cost_width - net_width
        if budget > 0:
            net_suffix = _ansi_clip(f"  {_SEP_ANSI} {cdx}", budget)
    rest_line = _ansi_clip(rest, cost_width) if rest.strip() else None
    return (net_suffix, rest_line)
