"""cockpit-three-layer 變更的行為測試（版面／雙擊／歸位／JOBS 收合）。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    from textual.app import App as _TextualApp
    from textual.widgets import ListView

    HAS_TEXTUAL = hasattr(_TextualApp, "run_test")
except Exception:
    ListView = None  # type: ignore
    HAS_TEXTUAL = False

from paulshaclaw.cockpit.app import CockpitApp
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


class FakeActions:
    """錄呼叫序的 layout actions；fail_first_swap=True 時「生涯第一次」swap 拋錯。"""

    def __init__(self, fail_first_swap=False, fail_all_swaps=False):
        self.calls = []
        self._swap_count = 0
        self.fail_first_swap = fail_first_swap
        self.fail_all_swaps = fail_all_swaps

    def swap_selected_with_active(self, *, selected_pane_id, active_pane_id):
        self.calls.append(("swap", selected_pane_id, active_pane_id))
        self._swap_count += 1
        if self.fail_all_swaps or (self.fail_first_swap and self._swap_count == 1):
            raise RuntimeError("tmux swap failed (fake)")

    def focus_pane(self, pane_id):
        self.calls.append(("focus", pane_id))

    def return_to_cockpit(self, cockpit_pane_id):
        self.calls.append(("focus", cockpit_pane_id))

    def swaps(self):
        return [c for c in self.calls if c[0] == "swap"]


DEFAULT_PANES = (
    pane_record("%0", title="cockpit", active=True),
    pane_record("%1", title="slot", left=81, width=119, height=50),
    pane_record("%2", title="agent", top=25, height=12),
    pane_record("%3", title="pytest", top=38, height=12),
)


def make_app(actions=None, panes=DEFAULT_PANES, **extra):
    return CockpitApp.from_snapshot(
        panes=panes,
        cockpit_pane_id="%0",
        cockpit_session_name="main",
        jobs_by_pane={},
        actions=actions if actions is not None else FakeActions(),
        pane_loader=lambda *, cockpit_pane_id: panes,
        **extra,
    )


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class ThreeLayerLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_layer_order_and_no_detail(self):
        app = make_app()
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            self.assertFalse(list(app.query("#pane-detail")))
            banner = app.query_one("#brand-banner")
            work = app.query_one("#work-list")
            jobs = app.query_one("#global-jobs")
            self.assertLess(banner.region.y, work.region.y)
            self.assertLess(work.region.y, jobs.region.y)

    async def test_small_terminal_keeps_work_min_height(self):
        app = make_app()
        async with app.run_test(size=(80, 15)) as pilot:
            await pilot.pause()
            work = app.query_one("#work-list")
            self.assertGreaterEqual(work.region.height, 5)


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class EnterSingleAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_triggers_exactly_one_swap(self):
        actions = FakeActions()
        app = make_app(actions=actions)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
        self.assertEqual(len(actions.swaps()), 1)
        self.assertEqual(actions.swaps()[0], ("swap", "%2", "%1"))


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def selected_event(pane_id, list_id="work-list"):
    return SimpleNamespace(
        list_view=SimpleNamespace(id=list_id),
        item=SimpleNamespace(pane_id=pane_id),
    )


class DoubleClickTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.actions = FakeActions()
        self.app = make_app(actions=self.actions, clock=self.clock)

    def click(self, pane_id, list_id="work-list"):
        self.app.on_list_view_selected(selected_event(pane_id, list_id))

    def test_double_click_within_threshold_swaps_once(self):
        self.click("%2")
        self.clock.now += 0.2
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [("swap", "%2", "%1")])

    def test_slow_second_click_does_not_swap(self):
        self.click("%2")
        self.clock.now += 0.5
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click, ("%2", self.clock.now))

    def test_cross_row_does_not_swap_and_rerecords(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%3")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click[0], "%3")

    def test_active_row_click_interrupts_gesture(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%1")
        self.clock.now += 0.1
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click[0], "%2")

    def test_double_click_on_active_row_is_noop(self):
        self.click("%1")
        self.clock.now += 0.1
        self.click("%1")
        self.assertEqual(self.actions.swaps(), [])
        self.assertIsNone(self.app._last_click)

    def test_item_without_pane_id_interrupts_gesture(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click(None)
        self.assertIsNone(self.app._last_click)

    def test_non_work_list_event_does_not_touch_state(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2", list_id="other-list")
        self.clock.now += 0.1
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [("swap", "%2", "%1")])

    def test_triple_click_starts_new_cycle(self):
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2")
        self.assertEqual(len(self.actions.swaps()), 1)
        self.assertEqual(self.app._last_click[0], "%2")

    def test_mismatch_guard_downgrades_to_first_click(self):
        self.app.state = self.app.state.set_selection(1)
        self.click("%2")
        self.clock.now += 0.1
        self.click("%2")
        self.assertEqual(self.actions.swaps(), [])
        self.assertEqual(self.app._last_click[0], "%2")

    def test_enter_swap_clears_pending_click(self):
        self.click("%2")
        self.clock.now += 0.1
        self.app.action_swap_selected()
        n = len(self.actions.swaps())
        self.clock.now += 0.1
        self.click("%2")
        self.assertEqual(len(self.actions.swaps()), n)

    def test_blocked_modal_prevents_swap(self):
        with patch.object(self.app, "_help_modal_open", return_value=True):
            self.click("%2")
            self.clock.now += 0.1
            self.click("%2")
        self.assertEqual(self.actions.swaps(), [])


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class EventChainAndInvariantTests(unittest.IsolatedAsyncioTestCase):
    async def test_double_click_real_event_chain(self):
        clock = FakeClock()
        actions = FakeActions()
        app = make_app(actions=actions, clock=clock)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#row-2")
            clock.now += 0.1
            await pilot.click("#row-2")
            await pilot.pause()
        self.assertIn(("swap", "%2", "%1"), actions.calls)

    async def test_sole_listview_invariant_across_states(self):
        from textual.widgets import ListView as TextualListView

        app = make_app()
        app.manager_client = SimpleNamespace(
            read_status=lambda: {},
            submit_request=lambda *a, **k: None,
        )
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            def assert_sole():
                base = app.screen_stack[0]
                views = list(base.query(TextualListView))
                self.assertEqual(len(views), 1)
                self.assertEqual(views[0].id, "work-list")
                for screen in app.screen_stack[1:]:
                    self.assertEqual(len(list(screen.query(TextualListView))), 0)

            assert_sole()
            await pilot.press("question_mark")
            await pilot.pause()
            assert_sole()
            await pilot.press("escape")
            await pilot.pause()
            assert_sole()
            await pilot.press("m")
            await pilot.pause()
            assert_sole()
            await pilot.press("escape")
            await pilot.pause()
            assert_sole()
            app._on_refresh_tick()
            assert_sole()


class RestoreBeforeSwapTests(unittest.TestCase):
    def setUp(self):
        self.actions = FakeActions()
        self.app = make_app(actions=self.actions, clock=FakeClock())

    def test_plain_activate_sets_record(self):
        self.app._activate("%2", "%1")
        self.assertEqual(self.actions.calls, [("swap", "%2", "%1"), ("focus", "%2")])
        self.assertEqual(self.app._displacement, ("%2", "%1"))

    def test_second_activate_restores_first(self):
        self.app._activate("%2", "%1")
        self.actions.calls.clear()
        self.app._activate("%3", "%1")
        self.assertEqual(
            self.actions.calls,
            [("swap", "%1", "%2"), ("swap", "%3", "%1"), ("focus", "%3")],
        )
        self.assertEqual(self.app._displacement, ("%3", "%1"))

    def test_activating_displaced_completes_via_restore_only(self):
        self.app._displacement = ("%2", "%1")
        self.app._activate("%1", "%2")
        self.assertEqual(self.actions.calls, [("swap", "%1", "%2")])
        self.assertIsNone(self.app._displacement)

    def test_restore_failure_aborts_activation(self):
        self.app.notify = Mock()
        self.actions.fail_first_swap = True
        self.app._displacement = ("%2", "%1")
        self.app._activate("%3", "%1")
        self.assertEqual(len(self.actions.swaps()), 1)
        self.assertIsNone(self.app._displacement)
        self.app.notify.assert_called()
        self.actions.calls.clear()
        self.app._activate("%3", "%1")
        self.assertEqual(self.actions.swaps(), [("swap", "%3", "%1")])

    def test_restore_failure_with_displaced_target_also_aborts(self):
        self.actions.fail_first_swap = True
        self.app._displacement = ("%2", "%1")
        self.app._activate("%1", "%2")
        self.assertEqual(len(self.actions.swaps()), 1)
        self.assertIsNone(self.app._displacement)

    def test_missing_recorded_pane_drops_record_silently(self):
        self.app._displacement = ("%9", "%8")
        self.app._activate("%2", "%1")
        self.assertEqual(self.actions.calls, [("swap", "%2", "%1"), ("focus", "%2")])
        self.assertEqual(self.app._displacement, ("%2", "%1"))

    def test_main_swap_failure_keeps_record_cleared(self):
        self.app.notify = Mock()
        self.actions.fail_all_swaps = True
        self.app._activate("%2", "%1")
        self.assertIsNone(self.app._displacement)
        self.app.notify.assert_called()

    def test_action_swap_selected_routes_through_activate(self):
        self.app.action_swap_selected()
        self.assertEqual(self.actions.swaps(), [("swap", "%2", "%1")])
        self.assertEqual(self.app._displacement, ("%2", "%1"))


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsToggleTests(unittest.IsolatedAsyncioTestCase):
    def _status(self):
        return {"in_flight": [{"slice_id": "s1", "state": "running"}]}

    async def test_toggle_collapse_and_expand(self):
        app = make_app()
        app.manager_client = SimpleNamespace(
            read_status=self._status, submit_request=lambda *a, **k: None
        )
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            jobs = app.query_one("#global-jobs")
            expanded = jobs.region.height
            await pilot.press("j")
            await pilot.pause()
            self.assertLessEqual(jobs.region.height, 3)
            self.assertIn("▸", str(jobs.border_title))
            self.assertIn("1 slices", str(jobs.border_title))
            await pilot.press("j")
            await pilot.pause()
            self.assertEqual(jobs.region.height, expanded)

    async def test_toggle_blocked_while_modal_open(self):
        app = make_app()
        app.manager_client = SimpleNamespace(
            read_status=self._status, submit_request=lambda *a, **k: None
        )
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            self.assertFalse(app._jobs_collapsed)
            await pilot.press("escape")
