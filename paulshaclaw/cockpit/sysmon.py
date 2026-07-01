"""Cockpit 頂部系統監控（htop 風：CPU 整體均值 / Mem / Swap / Tasks），讀 /proc。

純函式 + fail-soft：/proc 讀取或解析失敗一律回可安全略過的結果，絕不影響 TUI。
CPU% 需兩次 /proc/stat 取樣差值，故 read_stats 需帶入上一次的 cpu 快照。
"""
from __future__ import annotations

import os
import re

# htop 風配色（依使用率門檻）
_GREEN = "\033[38;5;46m"
_YELLOW = "\033[38;5;226m"
_RED = "\033[38;5;196m"
_DIM = "\033[38;5;240m"
_LBL = "\033[1;38;5;250m"
_X = "\033[0m"


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def parse_cpu_total(stat_text: str):
    """自 /proc/stat 首行 ``cpu ...`` 回 (total_jiffies, idle_jiffies)；失敗回 None。"""
    for line in stat_text.splitlines():
        if line.startswith("cpu "):
            try:
                nums = [int(x) for x in line.split()[1:]]
            except ValueError:
                return None
            if len(nums) < 5:
                return None
            idle = nums[3] + nums[4]  # idle + iowait
            return (sum(nums), idle)
    return None


def cpu_percent(prev, cur):
    """兩次 (total, idle) 快照算整體 CPU 使用率 %；prev/cur 缺或 Δ總量≤0 回 None。"""
    if not prev or not cur:
        return None
    d_total = cur[0] - prev[0]
    d_idle = cur[1] - prev[1]
    if d_total <= 0:
        return None
    return max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))


def parse_meminfo(text: str) -> dict:
    """回 dict（kB）：MemTotal / MemAvailable / SwapTotal / SwapFree 等；缺項略過。"""
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+)\s*kB", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def parse_tasks(loadavg_text: str):
    """自 /proc/loadavg 第 4 欄 ``running/total`` 回 (running, total)；失敗回 None。"""
    parts = loadavg_text.split()
    if len(parts) >= 4 and "/" in parts[3]:
        r, _, t = parts[3].partition("/")
        try:
            return (int(r), int(t))
        except ValueError:
            return None
    return None


def read_stats(cpu_prev=None, proc: str = "/proc"):
    """讀一次系統狀態。回 ``(stats, cpu_snapshot)``；stats 缺項為 None。fail-soft。"""
    cur_cpu = parse_cpu_total(_read(f"{proc}/stat"))
    mem = parse_meminfo(_read(f"{proc}/meminfo"))
    tasks = parse_tasks(_read(f"{proc}/loadavg"))
    mt, ma = mem.get("MemTotal"), mem.get("MemAvailable")
    st, sf = mem.get("SwapTotal"), mem.get("SwapFree")
    stats = {
        "cpu": cpu_percent(cpu_prev, cur_cpu),
        "mem_used_kb": (mt - ma) if mt is not None and ma is not None else None,
        "mem_total_kb": mt,
        "swap_used_kb": (st - sf) if st is not None and sf is not None else None,
        "swap_total_kb": st,
        "tasks": tasks,
    }
    return stats, cur_cpu


def _hue(pct):
    if pct is None:
        return _DIM
    return _GREEN if pct < 50 else _YELLOW if pct < 80 else _RED


def _bar(pct, width, color):
    if pct is None:
        body = "?" * width
        return f"[{_DIM}{body}{_X}]" if color else f"[{body}]"
    filled = int(round(pct / 100.0 * width))
    filled = max(0, min(width, filled))
    body = "|" * filled + " " * (width - filled)
    return f"[{_hue(pct)}{body}{_X}]" if color else f"[{body}]"


def _gb(kb):
    return f"{kb / 1024 / 1024:.1f}G" if kb is not None else "?"


def format_stat_lines(stats: dict, *, color: bool | None = None, bar: int = 8) -> list[str]:
    """組出 4 列 htop 風監控字串：CPU / Mem / Swp / Tasks。``color`` 預設依 NO_COLOR。"""
    if color is None:
        color = not os.environ.get("NO_COLOR")
    lbl = (lambda s: f"{_LBL}{s}{_X}") if color else (lambda s: s)

    cpu = stats.get("cpu")
    mt, mu = stats.get("mem_total_kb"), stats.get("mem_used_kb")
    st, su = stats.get("swap_total_kb"), stats.get("swap_used_kb")
    mp = (mu / mt * 100.0) if mt and mu is not None else None
    sp = (su / st * 100.0) if st and su is not None else None
    tasks = stats.get("tasks")

    return [
        f"{lbl('CPU')} {_bar(cpu, bar, color)} {'  --' if cpu is None else f'{cpu:4.1f}%'}",
        f"{lbl('Mem')} {_bar(mp, bar, color)} {_gb(mu)}/{_gb(mt)}",
        f"{lbl('Swp')} {_bar(sp, bar, color)} {_gb(su)}/{_gb(st)}",
        f"{lbl('Tasks')} {tasks[1]} ({tasks[0]} run)" if tasks else f"{lbl('Tasks')} --",
    ]
