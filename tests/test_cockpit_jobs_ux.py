"""JOBS 面板 Tree 化後的 UX 行為測試（#264 焦點/鍵盤/滑鼠/捲動）。

新版 JOBS（paulshaclaw/cockpit/jobs_panel.JobsPanel）是可 focus 的 Tree，
取代舊的不可互動 Static——這裡驗證的是「操作起來對不對」，內容渲染的斷言
在 tests/test_stage11_operator_cockpit.py 已覆蓋，不重複。
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

try:
    from textual.app import App as _TextualApp

    HAS_TEXTUAL = hasattr(_TextualApp, "run_test")
except Exception:  # pragma: no cover - textual 未安裝時整檔跳過
    HAS_TEXTUAL = False

from paulshaclaw.cockpit.app import CockpitApp
from paulshaclaw.cockpit.actions import LayoutActionService
from paulshaclaw.cockpit.models import PaneRecord


def pane_record(
    pane_id,
    *,
    session_name="main",
    window_index="0",
    title="pane",
    command="bash",
    left=0,
    top=0,
    width=80,
    height=24,
    active=False,
    summary="",
):
    return PaneRecord(
        pane_id=pane_id,
        session_name=session_name,
        window_index=window_index,
        title=title,
        command=command,
        left=left,
        top=top,
        width=width,
        height=height,
        active=active,
        summary=summary,
    )


# %0 是 cockpit 本身；%1 是它的 active slot；%2/%3 是 WORK 候選列（既有測試沿用的版面）。
DEFAULT_PANES = (
    pane_record("%0", title="cockpit", active=True),
    pane_record("%1", title="slot", left=81, width=119, height=50),
    pane_record("%2", title="agent", top=25, height=12),
    pane_record("%3", title="pytest", top=38, height=12),
)


def make_app(*, manager_status=None, panes=DEFAULT_PANES, **extra) -> CockpitApp:
    app = CockpitApp.from_snapshot(
        panes=panes,
        cockpit_pane_id="%0",
        cockpit_session_name="main",
        jobs_by_pane={},
        actions=LayoutActionService(),
        pane_loader=lambda *, cockpit_pane_id: panes,
        **extra,
    )
    status = manager_status if manager_status is not None else {"degraded": False}
    app.manager_client = SimpleNamespace(
        read_status=lambda: status, submit_request=lambda *a, **k: None
    )
    return app


def _ready_group_status(count: int) -> dict:
    """`count` 個互不相干的 slice——各自成一群，state 皆為 routine 的 ready，
    不會觸發 needs_human 排序或預設展開，方便單純驗證捲動/游標移動。"""
    return {"ready": [f"routine-slice-{index}" for index in range(count)], "degraded": False}


def _multi_phase_status() -> dict:
    """單一 workflow 的兩個 phase：收成一群、非 needs_human，預設應收合。"""
    return {
        "ready": [
            {"slice_id": "wf-aaaaaaaaaa-subagent-build", "state": "ready"},
            {"slice_id": "wf-aaaaaaaaaa-code-review", "state": "ready"},
        ],
        "degraded": False,
    }


def _needs_human_status() -> dict:
    """單筆 needs_human 帶 reason/next_actions：預設應展開且 detail child 可見。"""
    return {
        "attention": [
            {
                "slice_id": "slice-needs-human",
                "job_state": "exited",
                "reason": "candidate-worktree-dirty",
                "next_actions": ["retry-build"],
            }
        ],
        "degraded": False,
    }


async def _tab_until(pilot, app, target_id: str, *, max_presses: int = 6) -> bool:
    """連按 tab 直到 focus 落在 `target_id`（或超過上限）；回傳是否成功命中。

    只有 #work-list 與 #global-jobs 兩個 focusable widget，理論上一次 tab 就會
    輪到對方，但 Header/Footer 未來若也變 focusable 不該讓測試脆得一按就炸。
    """
    for _ in range(max_presses):
        await pilot.press("tab")
        await pilot.pause()
        if getattr(app.focused, "id", None) == target_id:
            return True
    return False


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsFocusTests(unittest.IsolatedAsyncioTestCase):
    async def test_tab_cycles_focus_into_jobs_panel_and_back(self) -> None:
        app = make_app(manager_status=_ready_group_status(3))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(getattr(app.focused, "id", None), "work-list")

            reached_jobs = await _tab_until(pilot, app, "global-jobs")
            self.assertTrue(reached_jobs, "tab 應該最終會輪到 #global-jobs")

            reached_work = await _tab_until(pilot, app, "work-list")
            self.assertTrue(reached_work, "再 tab 下去應該會輪回 #work-list")

    async def test_click_on_jobs_panel_moves_focus(self) -> None:
        app = make_app(manager_status=_ready_group_status(3))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(getattr(app.focused, "id", None), "work-list")

            await pilot.click("#global-jobs")
            await pilot.pause()

            self.assertEqual(getattr(app.focused, "id", None), "global-jobs")


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsKeyboardRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_down_in_jobs_panel_moves_tree_cursor_not_work_selection(self) -> None:
        app = make_app(manager_status=_ready_group_status(5))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            jobs = app.query_one("#global-jobs")
            selected_before = app.state.selected_pane
            cursor_before = jobs.cursor_line

            await _tab_until(pilot, app, "global-jobs")
            await pilot.press("down")
            await pilot.pause()

            # tree 游標動了……
            self.assertNotEqual(jobs.cursor_line, cursor_before)
            # ……但 WORK 的選取狀態完全沒被碰到，兩個清單互不干擾。
            self.assertEqual(app.state.selected_pane, selected_before)

    async def test_down_in_work_list_still_moves_work_selection(self) -> None:
        """既有行為不回歸：WORK 有 focus 時 down 仍動 WORK 選擇。"""
        app = make_app(manager_status=_ready_group_status(2))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(getattr(app.focused, "id", None), "work-list")
            selected_before = app.state.selected_pane

            await pilot.press("down")
            await pilot.pause()

            self.assertNotEqual(app.state.selected_pane, selected_before)


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsExpandCollapseTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_toggles_expand_on_multi_phase_group(self) -> None:
        app = make_app(manager_status=_multi_phase_status())
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            jobs = app.query_one("#global-jobs")
            (group_node,) = jobs.root.children
            # 非 needs_human 的多 phase 群預設收合（契約：只有 needs_human 才 expand=True）。
            self.assertFalse(group_node.is_expanded)

            await _tab_until(pilot, app, "global-jobs")
            await pilot.press("enter")
            await pilot.pause()

            self.assertTrue(group_node.is_expanded)

    async def test_needs_human_group_defaults_expanded_with_visible_detail_child(self) -> None:
        app = make_app(manager_status=_needs_human_status())
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            jobs = app.query_one("#global-jobs")
            (group_node,) = jobs.root.children

            self.assertTrue(group_node.is_expanded)
            self.assertTrue(len(group_node.children) >= 1, "needs_human 群應該掛出 detail child")
            detail_text = str(group_node.children[0].label)
            self.assertIn("↳", detail_text)
            self.assertIn("candidate-worktree-dirty", detail_text)


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsScrollingTests(unittest.IsolatedAsyncioTestCase):
    async def test_scrolling_past_max_height_advances_scroll_offset(self) -> None:
        # max_height 展開態是 12：25 個各自成群的 slice 保證超過一頁，逼出橫/直向捲動。
        app = make_app(manager_status=_ready_group_status(25))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            jobs = app.query_one("#global-jobs")
            self.assertEqual(jobs.scroll_offset.y, 0)

            await _tab_until(pilot, app, "global-jobs")
            for _ in range(30):
                await pilot.press("down")
            await pilot.pause()

            self.assertGreater(jobs.scroll_offset.y, 0)
