"""Cockpit 頂部系統監控（htop 風分段色 meter），讀 /proc。

5 列對齊破蝦哥 banner：
  CPU  綠 user / 藍 nice / 紅 system
  Mem  綠 used / 紫 shared / 藍 buffers / 黃 cache
  Swp  紅 used / 黃 cache
  I/O  單段（依 util% 門檻上色）
  Net  ↓X ↑Y MB/s（速率，不用 %）

CPU% / I/O% / Net 速率需前後兩次快照差值，採快照模型：
``read_snapshot()`` 取原始計數 + 單調時鐘，``compute_stats(prev, cur)`` 算可讀值。
純函式 + fail-soft：任何 /proc 讀取或解析失敗都回可安全略過結果，絕不影響 TUI。
"""
from __future__ import annotations

import os
import re
import time

# htop 風配色
_GREEN = "\033[38;5;46m"    # used / user
_MAGENTA = "\033[38;5;129m"  # shared
_BLUE = "\033[38;5;33m"     # buffers / nice
_YELLOW = "\033[38;5;226m"  # cache
_RED = "\033[38;5;196m"     # swap used / system
_DIM = "\033[38;5;240m"
_LBL = "\033[1;38;5;250m"
_NET = "\033[38;5;45m"
_X = "\033[0m"

_WHOLE_DISK = re.compile(r"^(sd[a-z]+|nvme\d+n\d+|vd[a-z]+|xvd[a-z]+|mmcblk\d+)$")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def parse_cpu(stat_text: str):
    """自 /proc/stat 首行 ``cpu ...`` 回原始 jiffies 串列 [user,nice,system,idle,iowait,...]；失敗回 None。"""
    for line in stat_text.splitlines():
        if line.startswith("cpu "):
            try:
                nums = [int(x) for x in line.split()[1:]]
            except ValueError:
                return None
            return nums if len(nums) >= 7 else None
    return None


def parse_disk_ioticks(text: str):
    """加總各實體磁碟 io_ticks（/proc/diskstats 第 13 欄）；無資料回 None。"""
    total = None
    for line in text.splitlines():
        f = line.split()
        if len(f) > 12 and _WHOLE_DISK.match(f[2]):
            try:
                total = (total or 0) + int(f[12])
            except ValueError:
                pass
    return total


def parse_netdev(text: str):
    """加總非 lo 介面的 (rx_bytes, tx_bytes)；無資料回 None。"""
    rx = tx = None
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        if name.strip() == "lo":
            continue
        f = rest.split()
        if len(f) >= 9:
            try:
                rx = (rx or 0) + int(f[0])
                tx = (tx or 0) + int(f[8])
            except ValueError:
                pass
    return None if rx is None else (rx, tx)


def parse_meminfo(text: str) -> dict:
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+)\s*kB", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def read_snapshot(proc: str = "/proc", *, clock=time.monotonic) -> dict:
    """取一次原始計數快照（含單調時鐘）。fail-soft：缺項為 None。"""
    return {
        "t": clock(),
        "cpu": parse_cpu(_read(f"{proc}/stat")),
        "io": parse_disk_ioticks(_read(f"{proc}/diskstats")),
        "net": parse_netdev(_read(f"{proc}/net/dev")),
        "mem": parse_meminfo(_read(f"{proc}/meminfo")),
    }


def _cpu_breakdown(prev_cpu, cur_cpu):
    """回 {user,nice,system,pct}（皆為佔 Δtotal 的 %，pct=busy%）；不可算回 None。"""
    if not prev_cpu or not cur_cpu:
        return None
    d = [c - p for c, p in zip(cur_cpu, prev_cpu)]
    if any(x < 0 for x in d):  # counter reset
        return None
    total = sum(d)
    if total <= 0:
        return None
    idle = d[3] + d[4]  # idle + iowait
    system = d[2] + d[5] + d[6]  # system + irq + softirq
    f = lambda v: max(0.0, min(100.0, v / total * 100.0))
    return {"user": f(d[0]), "nice": f(d[1]), "system": f(system), "pct": f(total - idle)}


def _mem_breakdown(mem: dict):
    """htop 記憶體分段（kB）：used/shared/buffers/cache/total 與 pct（非 free 佔比）。缺欄回 None。"""
    mt, mf = mem.get("MemTotal"), mem.get("MemFree")
    if not mt or mf is None:
        return None
    buffers = mem.get("Buffers", 0)
    shmem = mem.get("Shmem", 0)
    cache = max(0, mem.get("Cached", 0) + mem.get("SReclaimable", 0) - shmem)
    used = max(0, mt - mf - buffers - cache - shmem)
    return {"used": used, "shared": shmem, "buffers": buffers, "cache": cache,
            "total": mt, "pct": (mt - mf) / mt * 100.0}


def _swap_breakdown(mem: dict):
    st, sf = mem.get("SwapTotal"), mem.get("SwapFree")
    if not st or sf is None:
        return None
    cached = mem.get("SwapCached", 0)
    used = max(0, st - sf - cached)
    return {"used": used, "cache": cached, "total": st, "pct": (st - sf) / st * 100.0}


def compute_stats(prev: dict | None, cur: dict) -> dict:
    """由前後兩快照算 htop 風分段資料 dict。fail-soft：缺值為 None。"""
    dt = (cur["t"] - prev["t"]) if prev else None
    mem = cur.get("mem") or {}

    io = None
    if prev and dt and dt > 0 and prev.get("io") is not None and cur.get("io") is not None:
        d = cur["io"] - prev["io"]
        if d >= 0:
            io = max(0.0, min(100.0, d / (dt * 1000.0) * 100.0))

    net_rx = net_tx = None
    if prev and dt and dt > 0 and prev.get("net") and cur.get("net"):
        drx = cur["net"][0] - prev["net"][0]
        dtx = cur["net"][1] - prev["net"][1]
        if drx >= 0 and dtx >= 0:
            net_rx, net_tx = drx / dt, dtx / dt

    return {
        "cpu": _cpu_breakdown(prev.get("cpu") if prev else None, cur.get("cpu")),
        "mem": _mem_breakdown(mem),
        "swap": _swap_breakdown(mem),
        "io": io,
        "net_rx_bps": net_rx,
        "net_tx_bps": net_tx,
    }


# ---- 呈現 ----

def _hue(pct):
    if pct is None:
        return _DIM
    return _GREEN if pct < 50 else _YELLOW if pct < 80 else _RED


def _seg_bar(segments, width, color):
    """分段色橫條。segments=[(frac_of_bar, color), ...]（frac 為佔整條的比例，總和≤1）。"""
    width = max(1, width)
    if not color:
        filled = min(width, round(sum(f for f, _ in segments) * width))
        return "[" + "|" * filled + " " * (width - filled) + "]"
    body, prev_cell, acc = "", 0, 0.0
    for frac, col in segments:
        acc += frac
        cur_cell = min(width, int(round(acc * width)))
        n = max(0, cur_cell - prev_cell)
        if n:
            body += f"{col}{'|' * n}{_X}"
        prev_cell = cur_cell
    return "[" + body + " " * (width - prev_cell) + "]"


def _pctstr(pct):
    return "  --" if pct is None else f"{round(pct):3d}%"


def _mbs(bps):
    return "--" if bps is None else f"{bps / 1e6:.1f}"


def format_stat_lines(stats: dict, *, bar_width: int = 12, color: bool | None = None) -> list[str]:
    """組出 5 列 htop 風監控字串。``bar_width`` 為橫條可用寬（呼叫端依 pane 寬算）。"""
    if color is None:
        color = not os.environ.get("NO_COLOR")
    lbl = (lambda s: f"{_LBL}{s}{_X}") if color else (lambda s: s)
    net_c = (lambda s: f"{_NET}{s}{_X}") if color else (lambda s: s)

    def line(label, segs, pct):
        return f"{lbl(label)} {_seg_bar(segs, bar_width, color)} {_pctstr(pct)}"

    cpu, mem, swap = stats.get("cpu"), stats.get("mem"), stats.get("swap")
    cpu_segs = ([(cpu["user"] / 100, _GREEN), (cpu["nice"] / 100, _BLUE),
                 (cpu["system"] / 100, _RED)] if cpu else [])
    mem_segs = ([(mem[k] / mem["total"], c) for k, c in
                 (("used", _GREEN), ("shared", _MAGENTA), ("buffers", _BLUE), ("cache", _YELLOW))]
                if mem else [])
    swap_segs = ([(swap[k] / swap["total"], c) for k, c in (("used", _RED), ("cache", _YELLOW))]
                 if swap else [])
    io = stats.get("io")
    io_segs = [(io / 100, _hue(io))] if io is not None else []

    return [
        line("CPU", cpu_segs, cpu["pct"] if cpu else None),
        line("Mem", mem_segs, mem["pct"] if mem else None),
        line("Swp", swap_segs, swap["pct"] if swap else None),
        line("I/O", io_segs, io),
        f"{lbl('Net')} {net_c('↓' + _mbs(stats.get('net_rx_bps')))} "
        f"{net_c('↑' + _mbs(stats.get('net_tx_bps')))} MB/s",
    ]
