"""Cockpit 頂部系統監控（htop 風），讀 /proc。

呈現 5 列，對齊破蝦哥 banner 5 列：
  CPU / Mem / Swp / I/O 用 ``[bar] NN%``（bar 寬由呼叫端依終端寬度給）；
  Net 顯示上下行速率 ``↓X ↑Y MB/s``（不用 %）。

CPU% / I/O% / Net 速率皆需兩次取樣差值，故採「快照」模型：
``read_snapshot()`` 取一次原始計數 + 單調時鐘，``compute_stats(prev, cur)`` 算出可讀數值。
純函式 + fail-soft：任何 /proc 讀取或解析失敗都回可安全略過的結果，絕不影響 TUI。
"""
from __future__ import annotations

import os
import re
import time

# htop 風配色（依使用率門檻）
_GREEN = "\033[38;5;46m"
_YELLOW = "\033[38;5;226m"
_RED = "\033[38;5;196m"
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
            return (sum(nums), nums[3] + nums[4])  # total, idle+iowait
    return None


def parse_disk_ioticks(text: str):
    """加總各實體磁碟 io_ticks（/proc/diskstats 第 13 欄，ms doing I/O）；無資料回 None。"""
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
        "cpu": parse_cpu_total(_read(f"{proc}/stat")),
        "io": parse_disk_ioticks(_read(f"{proc}/diskstats")),
        "net": parse_netdev(_read(f"{proc}/net/dev")),
        "mem": parse_meminfo(_read(f"{proc}/meminfo")),
    }


def _pct(prev_v, cur_v, span):
    """差值 / span * 100，夾在 0~100；缺值或 span≤0 回 None。"""
    if prev_v is None or cur_v is None or not span or span <= 0:
        return None
    d = cur_v - prev_v
    if d < 0:
        return None
    return max(0.0, min(100.0, d / span * 100.0))


def compute_stats(prev: dict | None, cur: dict) -> dict:
    """由前後兩快照算出可讀數值 dict。fail-soft：缺值為 None。"""
    dt = (cur["t"] - prev["t"]) if prev else None

    cpu = None
    if prev and prev.get("cpu") and cur.get("cpu"):
        d_total = cur["cpu"][0] - prev["cpu"][0]
        cpu = _pct(prev["cpu"][1], cur["cpu"][1], d_total)
        cpu = (100.0 - cpu) if cpu is not None else None  # idle 佔比 → 使用率

    io = None
    if prev and dt:
        io = _pct(prev.get("io"), cur.get("io"), dt * 1000.0)  # io_ticks(ms) / 間隔(ms)

    net_rx = net_tx = None
    if prev and dt and dt > 0 and prev.get("net") and cur.get("net"):
        drx = cur["net"][0] - prev["net"][0]
        dtx = cur["net"][1] - prev["net"][1]
        if drx >= 0 and dtx >= 0:
            net_rx, net_tx = drx / dt, dtx / dt  # bytes/s

    mem = cur.get("mem") or {}
    mt, ma = mem.get("MemTotal"), mem.get("MemAvailable")
    st, sf = mem.get("SwapTotal"), mem.get("SwapFree")
    return {
        "cpu": cpu,
        "mem": ((mt - ma) / mt * 100.0) if mt and ma is not None else None,
        "swap": ((st - sf) / st * 100.0) if st and sf is not None else None,
        "io": io,
        "net_rx_bps": net_rx,
        "net_tx_bps": net_tx,
    }


def _hue(pct):
    if pct is None:
        return _DIM
    return _GREEN if pct < 50 else _YELLOW if pct < 80 else _RED


def _bar(pct, width, color):
    width = max(1, width)
    if pct is None:
        body = "?" * width if width > 1 else "?"
        return f"[{_DIM}{body}{_X}]" if color else f"[{body}]"
    filled = max(0, min(width, int(round(pct / 100.0 * width))))
    body = "|" * filled + " " * (width - filled)
    return f"[{_hue(pct)}{body}{_X}]" if color else f"[{body}]"


def _bar_line(label, pct, width, color, lbl):
    val = "  --" if pct is None else f"{round(pct):3d}%"
    return f"{lbl(label)} {_bar(pct, width, color)} {val}"


def _mbs(bps):
    return "--" if bps is None else f"{bps / 1e6:.1f}"


def format_stat_lines(stats: dict, *, bar_width: int = 12, color: bool | None = None) -> list[str]:
    """組出 5 列監控字串。``bar_width`` 為橫條可用寬（呼叫端依終端寬度算）。"""
    if color is None:
        color = not os.environ.get("NO_COLOR")
    lbl = (lambda s: f"{_LBL}{s}{_X}") if color else (lambda s: s)
    net_c = (lambda s: f"{_NET}{s}{_X}") if color else (lambda s: s)
    return [
        _bar_line("CPU", stats.get("cpu"), bar_width, color, lbl),
        _bar_line("Mem", stats.get("mem"), bar_width, color, lbl),
        _bar_line("Swp", stats.get("swap"), bar_width, color, lbl),
        _bar_line("I/O", stats.get("io"), bar_width, color, lbl),
        f"{lbl('Net')} {net_c('↓' + _mbs(stats.get('net_rx_bps')))} "
        f"{net_c('↑' + _mbs(stats.get('net_tx_bps')))} MB/s",
    ]
