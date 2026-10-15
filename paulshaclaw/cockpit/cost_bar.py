"""cockpit banner 的 cost footer 列。

唯讀消費者：讀 Stage 8 cost 已 cache 的 snapshot（由 Claude Code statusLine 每次刷新
時寫入），渲染成 ANSI 前景色（無背景色）的一列，接在 sysmon 之後。**絕不** 呼叫
``build_current_snapshot``（會打網路 chatgpt.com / api.github.com，卡住 TUI）。全程
fail-soft：任何錯誤都回 None，不擋 banner。
"""

from __future__ import annotations

from paulshaclaw.cost.cache import SnapshotCache
from paulshaclaw.cost.config import load_cost_config
from paulshaclaw.cost.formatter import format_cockpit_footer
from paulshaclaw.cost.models import CostSnapshot
from paulshaclaw.cost.status import _filter_snapshot_by_enabled, _mark_snapshot_stale


def read_snapshot() -> CostSnapshot | None:
    """讀已 cache 的 cost snapshot（不重建、不打網路）。任何錯誤回 None。"""
    try:
        config = load_cost_config()
        cache = SnapshotCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
        snapshot = cache.read_if_fresh()
        if snapshot is None:
            stale = cache.read_stale()
            snapshot = _mark_snapshot_stale(stale) if stale is not None else None
        return _filter_snapshot_by_enabled(snapshot, config) if snapshot is not None else None
    except Exception:  # noqa: BLE001 - fail-soft，絕不擋 TUI
        return None


def cost_line() -> str | None:
    """回完整 ANSI cost footer，由 Textual 按內容寬自動換行；無資料/出錯回 None。"""
    snapshot = read_snapshot()
    if snapshot is None:
        return None
    try:
        line = format_cockpit_footer(snapshot)
    except Exception:  # noqa: BLE001 - fail-soft
        return None
    if not line.strip():
        return None
    return line
