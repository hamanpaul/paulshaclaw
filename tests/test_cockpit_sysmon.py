"""paulshaclaw.cockpit.sysmon 單測——注入假 /proc 內容，hermetic、不依賴真系統。"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from paulshaclaw.cockpit import sysmon


class ParseTests(unittest.TestCase):
    def test_cpu_total_idle(self):
        # cpu  user nice system idle iowait irq softirq...
        r = sysmon.parse_cpu_total("cpu  100 0 50 800 40 0 10\ncpu0 ...")
        self.assertEqual(r, (1000, 840))  # total=sum, idle=idle(800)+iowait(40)

    def test_cpu_total_malformed(self):
        self.assertIsNone(sysmon.parse_cpu_total("garbage"))
        self.assertIsNone(sysmon.parse_cpu_total("cpu  1 2"))  # <5 欄

    def test_cpu_percent(self):
        # Δtotal=100, Δidle=20 → 使用率 80%
        self.assertAlmostEqual(sysmon.cpu_percent((1000, 800), (1100, 820)), 80.0)

    def test_cpu_percent_guards(self):
        self.assertIsNone(sysmon.cpu_percent(None, (1, 1)))
        self.assertIsNone(sysmon.cpu_percent((1000, 800), (1000, 800)))  # Δtotal=0

    def test_meminfo(self):
        m = sysmon.parse_meminfo("MemTotal: 10181808 kB\nMemAvailable:  7606936 kB\nFoo: 1")
        self.assertEqual(m["MemTotal"], 10181808)
        self.assertEqual(m["MemAvailable"], 7606936)

    def test_tasks(self):
        self.assertEqual(sysmon.parse_tasks("0.52 0.45 0.40 3/784 2629117"), (3, 784))
        self.assertIsNone(sysmon.parse_tasks("0.5 0.4 0.3"))


class ReadStatsTests(unittest.TestCase):
    def _proc(self, tmp, stat):
        (Path(tmp) / "stat").write_text(stat, encoding="utf-8")
        (Path(tmp) / "meminfo").write_text(
            "MemTotal: 10000000 kB\nMemAvailable: 6000000 kB\n"
            "SwapTotal: 8000000 kB\nSwapFree: 5000000 kB\n", encoding="utf-8")
        (Path(tmp) / "loadavg").write_text("0.5 0.4 0.3 2/500 111\n", encoding="utf-8")
        return tmp

    def test_read_stats_full(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._proc(tmp, "cpu  100 0 50 800 40 0 10\n")
            stats, snap = sysmon.read_stats(None, proc=tmp)
            self.assertIsNone(stats["cpu"])  # 首次無 prev
            self.assertEqual(snap, (1000, 840))
            self.assertEqual(stats["mem_used_kb"], 4000000)   # 10M-6M
            self.assertEqual(stats["mem_total_kb"], 10000000)
            self.assertEqual(stats["swap_used_kb"], 3000000)  # 8M-5M
            self.assertEqual(stats["tasks"], (2, 500))
            # 第二次帶入 prev → CPU% 有值
            (Path(tmp) / "stat").write_text("cpu  150 0 70 820 40 0 10\n", encoding="utf-8")
            stats2, _ = sysmon.read_stats(snap, proc=tmp)
            self.assertIsNotNone(stats2["cpu"])

    def test_read_stats_missing_proc_is_safe(self):
        stats, snap = sysmon.read_stats(None, proc="/no/such/proc")
        self.assertIsNone(snap)
        self.assertIsNone(stats["cpu"])
        self.assertIsNone(stats["mem_total_kb"])
        self.assertIsNone(stats["tasks"])


class FormatTests(unittest.TestCase):
    STATS = {
        "cpu": 45.0, "mem_used_kb": 2500000, "mem_total_kb": 10000000,
        "swap_used_kb": 1200000, "swap_total_kb": 8000000, "tasks": (3, 784),
    }

    def test_four_lines_labelled(self):
        lines = sysmon.format_stat_lines(self.STATS, color=False)
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("CPU"))
        self.assertIn("45.0%", lines[0])
        self.assertTrue(lines[1].startswith("Mem"))
        self.assertIn("/9.5G", lines[1])  # 10000000kB ≈ 9.5G
        self.assertTrue(lines[2].startswith("Swp"))
        self.assertTrue(lines[3].startswith("Tasks"))
        self.assertIn("784 (3 run)", lines[3])

    def test_color_toggle(self):
        self.assertIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS, color=True)))
        self.assertNotIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS, color=False)))

    def test_no_color_env(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertNotIn("\x1b[", "".join(sysmon.format_stat_lines(self.STATS)))

    def test_none_values_safe(self):
        empty = {"cpu": None, "mem_used_kb": None, "mem_total_kb": None,
                 "swap_used_kb": None, "swap_total_kb": None, "tasks": None}
        lines = sysmon.format_stat_lines(empty, color=False)
        self.assertEqual(len(lines), 4)
        self.assertIn("--", lines[0])   # CPU --
        self.assertIn("?", lines[1])    # Mem ?/?
        self.assertIn("--", lines[3])   # Tasks --

    def test_bar_fills_with_load(self):
        low = sysmon.format_stat_lines({**self.STATS, "cpu": 0.0}, color=False)[0]
        high = sysmon.format_stat_lines({**self.STATS, "cpu": 100.0}, color=False)[0]
        self.assertNotIn("|", low)          # 0% 無填充
        self.assertIn("||||||||", high)     # 100% 滿條(8)


if __name__ == "__main__":
    unittest.main()
