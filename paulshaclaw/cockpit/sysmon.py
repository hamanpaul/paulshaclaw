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
    # total 只加前 8 欄（user..steal）：guest/guest_nice（idx 8/9）已含在 user/nice 內，
    # 再加總會重複計入 guest 時間、使 CPU% 失真（Copilot review；VM/guest 有值時尤然）。
    total = sum(d[:8])
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


def merge_stale(stats: dict, last_good: dict, stale_counts: dict, *, tolerance: int = 1) -> dict:
    """None 值短暫沿用上次有效值以 bridge 偶發缺樣（如 dt≤0、單次 counter-reset），
    但連續缺樣超過 ``tolerance`` 次即維持 None → 顯示 '--'（degraded）。

    這是刻意設計：避免 /proc 持久失效（來源消失/介面不見）卻長期顯示舊值＝假遙測
    （Codex adversarial review）。就地更新 ``last_good`` / ``stale_counts``。回合併後 dict。
    """
    merged = dict(stats)
    for k, v in stats.items():
        if v is not None:
            last_good[k] = v
            stale_counts[k] = 0
        else:
            stale_counts[k] = stale_counts.get(k, 0) + 1
            merged[k] = last_good[k] if (k in last_good and stale_counts[k] <= tolerance) else None
    return merged


# ---- 呈現 ----

def _hue(pct):
    if pct is None:
        return _DIM
    return _GREEN if pct < 50 else _YELLOW if pct < 80 else _RED


_TXT = _LBL   # overlay 數字落在長條空白處時的可讀中性色


def _human_kb(kb) -> str:
    """kB → 人類可讀（base-1024，K/M/G/T/P）；htop 風精度：<10 兩位、<100 一位、否則整數。
    ``None`` → ``'--'``。例：4300→'4.20M'、10182000→'9.71G'。"""
    if kb is None:
        return "--"
    v = float(kb)
    units = ("K", "M", "G", "T", "P")
    i = 0
    while v >= 1024.0 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    if v >= 100:
        s = f"{v:.0f}"
    elif v >= 10:
        s = f"{v:.1f}"
    else:
        s = f"{v:.2f}"
    return f"{s}{units[i]}"


def _pctstr(pct) -> str:
    """尾隨百分比欄（置於 ``]`` 右側）：固定 4 寬以四欄對齊。None → ``'  --'``。"""
    return "  --" if pct is None else f"{round(pct):3d}%"


def _mbs(bps):
    return "--" if bps is None else f"{bps / 1e6:.1f}"


def _meter_bar(segments, width, overlay, color, *, empty_color=_DIM):
    """htop 風 meter：左起以分段色 ``|`` 填滿，右對齊把 ``overlay``（實際用量／百分比）疊進長條內。

    變色邏輯（同 htop）：overlay 每個字元沿用其底層 cell 顏色——落在填色段→該段色、落在空白→中性
    可讀色，使數字與長條融為一體。回 ``'[' + body + ']'``。
    fail-soft：width 過窄時保留 overlay 右側（尾端，如 used/total 的 total），合右對齊語意。
    """
    width = max(1, width)
    chars = [" "] * width
    colors = [empty_color] * width
    # 1) 分段填色（左起）
    acc, prev_cell = 0.0, 0
    for frac, col in segments:
        acc += frac
        cur_cell = min(width, int(round(acc * width)))
        for c in range(prev_cell, cur_cell):
            chars[c] = "|"
            colors[c] = col
        prev_cell = cur_cell
    filled_before = [ch == "|" for ch in chars]
    # 2) 右對齊疊 overlay；width 過窄時保留右側尾端（used/total 的 total）以合右對齊語意（Copilot review PR #170）
    if overlay:
        text = overlay[-width:]
        start = width - len(text)
        for offset, ch in enumerate(text):
            pos = start + offset
            chars[pos] = ch
            if not filled_before[pos]:
                colors[pos] = _TXT
    # 3) 組字串
    if not color:
        return "[" + "".join(chars) + "]"
    body, run_col, run = "", None, ""
    for ch, col in zip(chars, colors):
        if col == run_col:
            run += ch
        else:
            if run:
                body += f"{run_col}{run}{_X}"
            run_col, run = col, ch
    if run:
        body += f"{run_col}{run}{_X}"
    return "[" + body + "]"


def format_stat_lines(stats: dict, *, bar_width: int = 12, color: bool | None = None) -> list[str]:
    """組出 5 列 htop 風監控字串：Mem/Swp 於長條內右對齊疊實際用量 used/total（依底層分段上色）；
    四欄（CPU/Mem/Swp/I/O）百分比一律置於 ``]`` 右側對齊。``bar_width`` 為長條可用寬（呼叫端依 pane 寬算）。"""
    if color is None:
        color = not os.environ.get("NO_COLOR")
    lbl = (lambda s: f"{_LBL}{s}{_X}") if color else (lambda s: s)
    net_c = (lambda s: f"{_NET}{s}{_X}") if color else (lambda s: s)

    def line(label, segs, overlay, pct):
        # 長條內疊用量（Mem/Swp）或留空（CPU/I/O）；百分比一律置於 ] 右側、四欄對齊。
        return f"{lbl(label)} {_meter_bar(segs, bar_width, overlay, color)} {_pctstr(pct)}"

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

    # Mem/Swp 疊實際用量 used/total（htop 風）；CPU/I/O 疊百分比。
    mem_txt = f"{_human_kb(mem['used'])}/{_human_kb(mem['total'])}" if mem else "--"
    swap_txt = f"{_human_kb(swap['used'])}/{_human_kb(swap['total'])}" if swap else "--"

    return [
        line("CPU", cpu_segs, "", cpu["pct"] if cpu else None),
        line("Mem", mem_segs, mem_txt, mem["pct"] if mem else None),
        line("Swp", swap_segs, swap_txt, swap["pct"] if swap else None),
        line("I/O", io_segs, "", io),
        f"{lbl('Net')} {net_c('↓' + _mbs(stats.get('net_rx_bps')))} "
        f"{net_c('↑' + _mbs(stats.get('net_tx_bps')))} MB/s",
    ]
