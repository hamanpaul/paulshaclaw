"""精緻面板重設計（cockpit + tui/view）之純函式與結構契約單測。

不啟動 Pilot（避免 textual 版本漂移的脆弱測試）；只驗證上色/摘要純函式、CSS 資產存在、
工作清單「純字串 key」與「彩色 renderable」逐列對齊，以及 tui 表格的邊框/glyph/NO_COLOR。
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paulshaclaw.cockpit import app as cockpit_app
from paulshaclaw.cockpit.app import (
    CockpitApp,
    format_session_summary,
    status_style,
)
from paulshaclaw.cockpit.models import JobSummary, PaneRecord
from paulshaclaw.cockpit.store import CockpitState
from paulshaclaw.tui.view import render_pane_task_view


def pane(pid, *, session="main", window="0", title="pane", command="bash",
         left=0, top=0, width=80, height=24):
    return PaneRecord(pid, session, window, title, command, left, top, width,
                      height, False, ())


class StatusStyleTests(unittest.TestCase):
    def test_known_statuses_map_to_glyph_and_semantic_color(self) -> None:
        self.assertEqual(status_style("running"), ("●", "#22C55E"))
        self.assertEqual(status_style("failed"), ("✗", "#EF4444"))
        self.assertEqual(status_style("done")[0], "✓")
        self.assertEqual(status_style("pending"), ("◔", "#FBBF24"))

    def test_case_insensitive(self) -> None:
        self.assertEqual(status_style("FAILED"), status_style("failed"))
        self.assertEqual(status_style("  Running  "), status_style("running"))

    def test_unknown_status_falls_back_to_neutral(self) -> None:
        self.assertEqual(status_style("banana"), ("•", "#94A3B8"))
        self.assertEqual(status_style(""), ("•", "#94A3B8"))


class SessionSummaryTests(unittest.TestCase):
    def test_counts_exclude_cockpit_pane_and_dedupe_sessions(self) -> None:
        panes = (
            pane("%0", session="main", title="cockpit", command="python", width=120, height=40),
            pane("%4", session="main", left=120, width=120, height=40),
            pane("%9", session="work", left=0, top=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")
        self.assertEqual(format_session_summary(state), "main · 2 panes · 2 sess")


class CssAssetTests(unittest.TestCase):
    def test_css_path_points_to_shipped_stylesheet(self) -> None:
        css = Path(cockpit_app.__file__).parent / CockpitApp.CSS_PATH
        self.assertTrue(css.is_file(), f"missing cockpit stylesheet: {css}")
        body = css.read_text(encoding="utf-8")
        # 語意色盤與面板選擇器須在位（避免有人誤刪造成無樣式回退）
        self.assertIn("#work-list", body)
        self.assertIn("#22C55E", body)  # run-green accent


class WorkListRenderingTests(unittest.TestCase):
    def _app(self):
        panes = (
            pane("%0", session="main", title="cockpit", command="python", width=120, height=40),
            pane("%4", session="main", title="active", left=120, width=120, height=40),
            pane("%1", session="main", title="agent1", command="node", top=40, width=80, height=20),
            pane("%2", session="beta", title="iperf", command="iperf3", left=80, top=40, width=80, height=20),
        )
        return CockpitApp.from_snapshot(
            panes=panes, cockpit_pane_id="%0", cockpit_session_name="main",
            jobs_by_pane={"%1": (JobSummary("registry", "running", "t1", "%1", "s1"),)},
            actions=SimpleNamespace(),
        )

    def test_plain_key_and_renderables_are_row_for_row_aligned(self) -> None:
        app = self._app()
        active = app.state.active_pane
        items = app._work_list_items(active)
        renderables = app._work_list_renderables(active)
        self.assertEqual(len(items), len(renderables))
        # 首列為 ACTIVE，且候選列各一
        self.assertTrue(items[0].startswith("● ACTIVE"))
        self.assertEqual(len(items), 1 + len(app.state.candidate_section))

    def test_set_border_none_subtitle_clears_stale_summary(self) -> None:
        # Copilot review PR #168：subtitle=None 須清空副標，不得殘留上一選取 pane 的摘要。
        widget = SimpleNamespace(border_title="old", border_subtitle="stale-iperf")
        CockpitApp._set_border(widget, "DETAIL", None)
        self.assertEqual(widget.border_title, "DETAIL")
        self.assertEqual(widget.border_subtitle, "")

    def test_running_pane_row_shows_status_token_in_plain_key(self) -> None:
        app = self._app()
        items = app._work_list_items(app.state.active_pane)
        joined = "\n".join(items)
        self.assertIn("%1", joined)
        self.assertIn("running", joined)  # job 狀態尾綴反映在純字串 key


class TuiTableViewTests(unittest.TestCase):
    def _config(self):
        return SimpleNamespace(pane_assignments=(
            SimpleNamespace(pane_id="%1", title="core", task_id="stage1-core", status="running"),
            SimpleNamespace(pane_id="%2", title="net", task_id="perf", status="failed"),
        ))

    @staticmethod
    def _stream(*, encoding: str, tty: bool):
        return SimpleNamespace(encoding=encoding, isatty=lambda: tty)

    def test_unicode_mode_has_box_borders_and_status_glyphs(self) -> None:
        out = render_pane_task_view(self._config(), color=False, unicode=True)
        self.assertIn("╭", out)
        self.assertIn("│", out)
        self.assertIn("╰", out)
        self.assertIn("● running", out)
        self.assertIn("✗ failed", out)
        self.assertNotIn("\x1b[", out)  # color=False → 無 ANSI

    def test_color_true_emits_ansi_but_keeps_cell_text(self) -> None:
        out = render_pane_task_view(self._config(), color=True, unicode=True)
        self.assertIn("\x1b[", out)
        self.assertIn("stage1-core", out)  # task 欄不著色，子字串完整
        self.assertIn("%1", out)

    def test_auto_ascii_safe_under_c_locale_tty(self) -> None:
        # 回歸（Codex review #168）：ascii 編碼的 TTY → 自動退回純 ASCII，不得含框線/glyph，
        # 且整串可用 ascii 編碼（等同 LC_ALL=C / PYTHONUTF8=0 不會 UnicodeEncodeError）。
        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "NO_COLOR"}, clear=True):
            out = render_pane_task_view(self._config(), stream=self._stream(encoding="ascii", tty=True))
        self.assertTrue(out.isascii())
        out.encode("ascii")  # 不得拋 UnicodeEncodeError
        self.assertNotIn("╭", out)
        self.assertNotIn("●", out)
        self.assertIn("+", out)
        self.assertIn("running", out)
        self.assertIn("failed", out)

    def test_auto_redirected_non_tty_has_no_ansi_even_without_no_color(self) -> None:
        # 回歸（Codex review #168）：非 TTY（pipe/log/Telegram）即使 NO_COLOR 未設，也不得洩 ANSI，
        # 且退回 ASCII 邊框。
        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "NO_COLOR"}, clear=True):
            out = render_pane_task_view(self._config(), stream=self._stream(encoding="utf-8", tty=False))
        self.assertNotIn("\x1b[", out)
        self.assertNotIn("╭", out)
        self.assertIn("+", out)

    def test_explicit_color_overrides_non_tty(self) -> None:
        out = render_pane_task_view(self._config(), color=True, stream=self._stream(encoding="utf-8", tty=False))
        self.assertIn("\x1b[", out)  # 呼叫端顯式要求 → 覆寫 TTY 閘

    def test_no_color_env_strips_ansi_on_tty(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            out = render_pane_task_view(self._config(), stream=self._stream(encoding="utf-8", tty=True))
        self.assertNotIn("\x1b[", out)


if __name__ == "__main__":
    unittest.main()
