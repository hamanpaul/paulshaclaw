"""paulshaclaw.cockpit.sysmon 單測——注入假 /proc + 假時鐘，hermetic。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paulshaclaw.cockpit import sysmon


class ParseTests(unittest.TestCase):
    def test_cpu_raw_nums(self):
        self.assertEqual(sysmon.parse_cpu("cpu  100 0 50 800 40 0 10\n"), [100, 0, 50, 800, 40, 0, 10])

    def test_cpu_malformed(self):
        self.assertIsNone(sysmon.parse_cpu("garbage"))
        self.assertIsNone(sysmon.parse_cpu("cpu  1 2 3"))  # <7 欄

    def test_disk_ioticks_whole_disks_only(self):
        text = (
            "   1   0 ram0 0 0 0 0 0 0 0 0 0 0 0 0\n"
            "   8   0 sda 1 2 3 4 5 6 7 8 9 100 11\n"
            "   8   1 sda1 1 2 3 4 5 6 7 8 9 999 11\n"   # 分割區 → 略過
            "   8  16 sdb 1 2 3 4 5 6 7 8 9 50 11\n"
        )
        self.assertEqual(sysmon.parse_disk_ioticks(text), 150)

    def test_netdev_excludes_lo(self):
        text = (
            "h\nh\n"
            "    lo: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0\n"
            "  eth0: 1000 5 0 0 0 0 0 0 2000 5 0 0 0 0 0 0\n"
        )
        self.assertEqual(sysmon.parse_netdev(text), (1000, 2000))


class ComputeTests(unittest.TestCase):
    MEMINFO = ("MemTotal: 10000 kB\nMemFree: 4000 kB\nBuffers: 500 kB\nCached: 1000 kB\n"
               "SReclaimable: 200 kB\nShmem: 100 kB\nSwapTotal: 8000 kB\nSwapFree: 6000 kB\n"
               "SwapCached: 500 kB\n")

    def _write(self, tmp, cpu, io, rx, tx):
        Path(tmp, "stat").write_text(cpu, encoding="utf-8")
        Path(tmp, "diskstats").write_text(f"  8 0 sda 1 2 3 4 5 6 7 8 9 {io} 11\n", encoding="utf-8")
        (Path(tmp) / "net").mkdir(exist_ok=True)
        (Path(tmp) / "net" / "dev").write_text(
            f"h\nh\n  eth0: {rx} 5 0 0 0 0 0 0 {tx} 5 0 0 0 0 0 0\n", encoding="utf-8")
        (Path(tmp) / "meminfo").write_text(self.MEMINFO, encoding="utf-8")

    def test_full_compute(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "cpu  100 0 50 800 40 0 10\n", io=100, rx=0, tx=0)
            prev = sysmon.read_snapshot(tmp, clock=lambda: 0.0)
            # cur：每欄皆 ≥ prev（避免 counter-reset）；Δtotal=160，busy=80 → CPU 50%
            self._write(tmp, "cpu  180 0 50 880 40 0 10\n", io=200, rx=1_000_000, tx=500_000)
            cur = sysmon.read_snapshot(tmp, clock=lambda: 1.0)
            s = sysmon.compute_stats(prev, cur)

            self.assertAlmostEqual(s["cpu"]["pct"], 50.0)
            self.assertAlmostEqual(s["cpu"]["user"], 50.0)  # Δuser 80 / Δtotal 160
            self.assertAlmostEqual(s["io"], 10.0)           # 100ms / 1000ms
            self.assertAlmostEqual(s["net_rx_bps"], 1_000_000.0)
            self.assertAlmostEqual(s["net_tx_bps"], 500_000.0)
            # mem 分段：used=10000-4000-500-(1000+200-100)-100=4300；cache=1100
            self.assertEqual(s["mem"]["used"], 4300)
            self.assertEqual(s["mem"]["cache"], 1100)
            self.assertEqual(s["mem"]["shared"], 100)
            self.assertAlmostEqual(s["mem"]["pct"], 60.0)
            # swap：used=8000-6000-500=1500；cache=500；pct=25
            self.assertEqual(s["swap"]["used"], 1500)
            self.assertEqual(s["swap"]["cache"], 500)
            self.assertAlmostEqual(s["swap"]["pct"], 25.0)

    def test_first_read_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "cpu  1 0 1 1 0 0 0\n", io=1, rx=1, tx=1)
            s = sysmon.compute_stats(None, sysmon.read_snapshot(tmp, clock=lambda: 5.0))
            self.assertIsNone(s["cpu"])
            self.assertIsNone(s["io"])
            self.assertIsNone(s["net_rx_bps"])
            self.assertIsNotNone(s["mem"])  # 瞬時值

    def test_counter_reset_none(self):
        prev = {"t": 0.0, "cpu": [9, 9, 9, 9, 9, 9, 9], "io": 500, "net": (999, 999), "mem": {}}
        cur = {"t": 1.0, "cpu": [1, 1, 1, 1, 1, 1, 1], "io": 100, "net": (5, 5), "mem": {}}
        s = sysmon.compute_stats(prev, cur)
        self.assertIsNone(s["cpu"])
        self.assertIsNone(s["io"])
        self.assertIsNone(s["net_rx_bps"])

    def test_missing_proc_safe(self):
        s = sysmon.compute_stats(None, sysmon.read_snapshot("/no/such", clock=lambda: 1.0))
        self.assertTrue(all(s[k] is None for k in ("cpu", "mem", "swap", "io", "net_rx_bps")))


class MergeStaleTests(unittest.TestCase):
    """回歸：valid → missing → 短暫 bridge → 持久缺樣降級 '--'（Codex adversarial review）。"""

    def test_bridges_one_miss_then_clears(self):
        last, stale = {}, {}
        self.assertEqual(sysmon.merge_stale({"cpu": 50.0}, last, stale)["cpu"], 50.0)
        # 第 1 次缺樣：bridge 上次有效值（避免偶發缺樣閃爍）
        self.assertEqual(sysmon.merge_stale({"cpu": None}, last, stale, tolerance=1)["cpu"], 50.0)
        # 第 2 次連續缺樣：超過容忍 → 降級為 None（顯示 '--'，非假遙測）
        self.assertIsNone(sysmon.merge_stale({"cpu": None}, last, stale, tolerance=1)["cpu"])
        # 持續缺樣不會回頭顯示舊值
        self.assertIsNone(sysmon.merge_stale({"cpu": None}, last, stale, tolerance=1)["cpu"])

    def test_valid_sample_resets_counter(self):
        last, stale = {}, {}
        sysmon.merge_stale({"cpu": 50.0}, last, stale)
        sysmon.merge_stale({"cpu": None}, last, stale, tolerance=1)   # count=1（bridge）
        self.assertEqual(sysmon.merge_stale({"cpu": 70.0}, last, stale)["cpu"], 70.0)  # reset
        self.assertEqual(stale["cpu"], 0)
        # reset 後又可 bridge 一次新值
        self.assertEqual(sysmon.merge_stale({"cpu": None}, last, stale, tolerance=1)["cpu"], 70.0)

    def test_none_without_history_stays_none(self):
        self.assertIsNone(sysmon.merge_stale({"io": None}, {}, {})["io"])

    def test_tolerance_zero_clears_immediately(self):
        last, stale = {}, {}
        sysmon.merge_stale({"cpu": 50.0}, last, stale)
        self.assertIsNone(sysmon.merge_stale({"cpu": None}, last, stale, tolerance=0)["cpu"])

    def test_cleared_metric_renders_dashes(self):
        # 端到端：持久缺樣經 merge → format 顯示 '--'（非舊值）
        last, stale = {}, {}
        sysmon.merge_stale({"cpu": {"user": 30.0, "nice": 0.0, "system": 10.0, "pct": 40.0}}, last, stale)
        merged = sysmon.merge_stale({"cpu": None}, last, stale, tolerance=0)
        line = sysmon.format_stat_lines(
            {**{"mem": None, "swap": None, "io": None, "net_rx_bps": None, "net_tx_bps": None}, **merged},
            bar_width=8, color=False)[0]
        self.assertIn("--", line)
        self.assertNotIn("40%", line)


class FormatTests(unittest.TestCase):
    STATS = {
        "cpu": {"user": 30.0, "nice": 5.0, "system": 10.0, "pct": 45.0},
        "mem": {"used": 4300, "shared": 100, "buffers": 500, "cache": 1100, "total": 10000, "pct": 60.0},
        "swap": {"used": 1500, "cache": 500, "total": 8000, "pct": 25.0},
        "io": 30.0, "net_rx_bps": 3_400_000.0, "net_tx_bps": 800_000.0,
    }

    def test_five_lines(self):
        lines = sysmon.format_stat_lines(self.STATS, bar_width=10, color=False)
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("CPU") and "45%" in lines[0])
        self.assertTrue(lines[1].startswith("Mem") and "60%" in lines[1])
        self.assertTrue(lines[2].startswith("Swp") and "25%" in lines[2])
        self.assertTrue(lines[3].startswith("I/O") and "30%" in lines[3])
        self.assertTrue(lines[4].startswith("Net"))
        self.assertIn("↓3.4", lines[4])
        self.assertIn("↑0.8", lines[4])

    def test_mem_has_htop_segment_colors(self):
        mem_line = sysmon.format_stat_lines(self.STATS, bar_width=40, color=True)[1]
        for col in (sysmon._GREEN, sysmon._MAGENTA, sysmon._BLUE, sysmon._YELLOW):
            self.assertIn(col, mem_line)  # 綠/紫/藍/黃 四段皆在

    def test_swap_has_red_and_yellow(self):
        swp = sysmon.format_stat_lines(self.STATS, bar_width=40, color=True)[2]
        self.assertIn(sysmon._RED, swp)
        self.assertIn(sysmon._YELLOW, swp)

    def test_bar_width_scales(self):
        full = sysmon.format_stat_lines({**self.STATS, "io": 100.0}, bar_width=20, color=False)[3]
        self.assertIn("|" * 20, full)
        empty = sysmon.format_stat_lines({**self.STATS, "io": 0.0}, bar_width=20, color=False)[3]
        self.assertNotIn("|", empty)

    def test_no_color_env(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertNotIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS)))

    def test_none_values_safe(self):
        empty = {"cpu": None, "mem": None, "swap": None, "io": None,
                 "net_rx_bps": None, "net_tx_bps": None}
        lines = sysmon.format_stat_lines(empty, bar_width=8, color=False)
        self.assertEqual(len(lines), 5)
        self.assertIn("--", lines[0])
        self.assertIn("↓--", lines[4])


if __name__ == "__main__":
    unittest.main()
