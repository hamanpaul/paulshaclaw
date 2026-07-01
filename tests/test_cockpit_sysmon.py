"""paulshaclaw.cockpit.sysmon 單測——注入假 /proc + 假時鐘，hermetic。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paulshaclaw.cockpit import sysmon


class ParseTests(unittest.TestCase):
    def test_cpu_total_idle(self):
        self.assertEqual(sysmon.parse_cpu_total("cpu  100 0 50 800 40 0 10\n"), (1000, 840))

    def test_cpu_total_malformed(self):
        self.assertIsNone(sysmon.parse_cpu_total("garbage"))
        self.assertIsNone(sysmon.parse_cpu_total("cpu  1 2"))

    def test_disk_ioticks_sums_whole_disks_only(self):
        text = (
            "   1   0 ram0 0 0 0 0 0 0 0 0 0 0 0 0\n"
            "   8   0 sda 1 2 3 4 5 6 7 8 9 100 11\n"      # f13(idx12)=100
            "   8   1 sda1 1 2 3 4 5 6 7 8 9 999 11\n"     # 分割區 → 略過
            "   8  16 sdb 1 2 3 4 5 6 7 8 9 50 11\n"       # f13=50
            "   7   0 loop0 0 0 0 0 0 0 0 0 0 0 0 0\n"
        )
        self.assertEqual(sysmon.parse_disk_ioticks(text), 150)  # 100+50，排除 sda1/ram/loop

    def test_netdev_excludes_lo(self):
        text = (
            "Inter-|  Receive | Transmit\n face |bytes ...\n"
            "    lo: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0\n"
            "  eth0: 1000 5 0 0 0 0 0 0 2000 5 0 0 0 0 0 0\n"
        )
        self.assertEqual(sysmon.parse_netdev(text), (1000, 2000))  # 只 eth0

    def test_meminfo(self):
        m = sysmon.parse_meminfo("MemTotal: 100 kB\nMemAvailable: 60 kB\n")
        self.assertEqual((m["MemTotal"], m["MemAvailable"]), (100, 60))


class SnapshotComputeTests(unittest.TestCase):
    def _write_proc(self, tmp, cpu, io, net_rx, net_tx):
        Path(tmp, "stat").write_text(cpu, encoding="utf-8")
        Path(tmp, "diskstats").write_text(f"   8   0 sda 1 2 3 4 5 6 7 8 9 {io} 11\n", encoding="utf-8")
        (Path(tmp) / "net").mkdir(exist_ok=True)
        (Path(tmp) / "net" / "dev").write_text(
            f"h\nh\n  eth0: {net_rx} 5 0 0 0 0 0 0 {net_tx} 5 0 0 0 0 0 0\n", encoding="utf-8")
        (Path(tmp) / "meminfo").write_text(
            "MemTotal: 10000 kB\nMemAvailable: 4000 kB\nSwapTotal: 8000 kB\nSwapFree: 6000 kB\n",
            encoding="utf-8")

    def test_snapshot_and_compute(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_proc(tmp, "cpu  100 0 50 800 40 0 10\n", io=100, net_rx=0, net_tx=0)
            prev = sysmon.read_snapshot(tmp, clock=lambda: 0.0)
            # cur: total 1100(Δ100)、idle+iowait 860(Δ20) → idle 20% → CPU 80%
            self._write_proc(tmp, "cpu  180 0 60 820 40 0 0\n", io=200, net_rx=1_000_000, net_tx=500_000)
            cur = sysmon.read_snapshot(tmp, clock=lambda: 1.0)  # dt=1s

            s = sysmon.compute_stats(prev, cur)
            # cpu: Δtotal=100, Δidle=20 → idle 20% → 使用率 80%
            self.assertAlmostEqual(s["cpu"], 80.0)
            # io: Δio_ticks=100ms / (1s*1000)=1000ms → 10%
            self.assertAlmostEqual(s["io"], 10.0)
            # net: 1_000_000 B / 1s = 1.0 MB/s；tx 0.5 MB/s
            self.assertAlmostEqual(s["net_rx_bps"], 1_000_000.0)
            self.assertAlmostEqual(s["net_tx_bps"], 500_000.0)
            self.assertAlmostEqual(s["mem"], 60.0)   # (10000-4000)/10000
            self.assertAlmostEqual(s["swap"], 25.0)  # (8000-6000)/8000

    def test_first_read_no_prev_all_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_proc(tmp, "cpu  1 0 1 1 0 0 0\n", io=1, net_rx=1, net_tx=1)
            cur = sysmon.read_snapshot(tmp, clock=lambda: 5.0)
            s = sysmon.compute_stats(None, cur)
            self.assertIsNone(s["cpu"])
            self.assertIsNone(s["io"])
            self.assertIsNone(s["net_rx_bps"])
            self.assertIsNotNone(s["mem"])  # mem 為瞬時值，無需差值

    def test_missing_proc_is_safe(self):
        cur = sysmon.read_snapshot("/no/such/proc", clock=lambda: 1.0)
        s = sysmon.compute_stats(None, cur)
        self.assertTrue(all(s[k] is None for k in ("cpu", "io", "net_rx_bps", "mem", "swap")))

    def test_counter_reset_gives_none(self):
        prev = {"t": 0.0, "cpu": None, "io": 500, "net": (999, 999), "mem": {}}
        cur = {"t": 1.0, "cpu": None, "io": 100, "net": (5, 5), "mem": {}}  # 計數倒退
        s = sysmon.compute_stats(prev, cur)
        self.assertIsNone(s["io"])
        self.assertIsNone(s["net_rx_bps"])


class FormatTests(unittest.TestCase):
    STATS = {"cpu": 45.0, "mem": 62.0, "swap": 15.0, "io": 30.0,
             "net_rx_bps": 3_400_000.0, "net_tx_bps": 800_000.0}

    def test_five_lines(self):
        lines = sysmon.format_stat_lines(self.STATS, bar_width=10, color=False)
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("CPU") and "45%" in lines[0])
        self.assertTrue(lines[1].startswith("Mem"))
        self.assertTrue(lines[2].startswith("Swp"))
        self.assertTrue(lines[3].startswith("I/O"))
        self.assertTrue(lines[4].startswith("Net"))
        self.assertIn("↓3.4", lines[4])
        self.assertIn("↑0.8", lines[4])
        self.assertIn("MB/s", lines[4])

    def test_bar_width_scales(self):
        wide = sysmon.format_stat_lines({**self.STATS, "cpu": 100.0}, bar_width=20, color=False)[0]
        self.assertIn("|" * 20, wide)     # 100% → 滿 20 格
        narrow = sysmon.format_stat_lines({**self.STATS, "cpu": 0.0}, bar_width=20, color=False)[0]
        self.assertNotIn("|", narrow)

    def test_color_toggle_and_no_color_env(self):
        self.assertIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS, color=True)))
        self.assertNotIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS, color=False)))
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertNotIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS)))

    def test_none_values_safe(self):
        empty = {"cpu": None, "mem": None, "swap": None, "io": None,
                 "net_rx_bps": None, "net_tx_bps": None}
        lines = sysmon.format_stat_lines(empty, bar_width=8, color=False)
        self.assertEqual(len(lines), 5)
        self.assertIn("--", lines[0])           # CPU --
        self.assertIn("?", lines[1])            # Mem 空條
        self.assertIn("↓--", lines[4])          # Net --


if __name__ == "__main__":
    unittest.main()
