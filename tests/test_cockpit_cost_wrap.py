"""Catch lost provider values in the actual Textual banner after layout/resize."""
from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from paulshaclaw.cockpit.app import CockpitApp
from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow


def snapshot():
    def windows(five, weekly):
        return {'five_hour': UsageWindow(five, None, '17:30'),
                'weekly': UsageWindow(weekly, None, '4d')}
    return CostSnapshot(datetime.now(timezone.utc), 'UTC', 'fresh', {
        'cdx': ProviderSnapshot('fresh', windows=windows(11, 22)),
        'cc': ProviderSnapshot('fresh', windows=windows(33, 44)),
        'cpt': ProviderSnapshot('fresh', accounts=(CopilotAccountUsage(
            'hamanpaul', 'haman', 'personal', None, 1500,
            'github_copilot_quota', percent_used=87),)),
        'agy': ProviderSnapshot('fresh', windows=windows(63, 74)),
    })


class CostWrapTests(IsolatedAsyncioTestCase):
    async def check_widths(self, widths):
        app = CockpitApp.from_snapshot(panes=(), cockpit_pane_id='%0',
            cockpit_session_name='test', jobs_by_pane={}, actions=None)
        with patch('paulshaclaw.cockpit.cost_bar.read_snapshot', return_value=snapshot()), \
             patch.object(app.manager_client, 'read_status', return_value={}):
            async with app.run_test(size=(widths[0], 49)) as pilot:
                for width in widths:
                    await pilot.resize_terminal(width, 49)
                    await pilot.pause()
                    banner = app.query_one('#brand-banner')
                    rows = [strip.text for strip in app.screen._compositor.render_strips()]
                    rows = rows[banner.region.y:banner.region.bottom]
                    visible = ''.join(''.join(rows).replace('│', '').split())
                    for value in ('cdx5h:11%(17:30)wk:22%(4d)',
                                  'cc5h:33%(17:30)wk:44%(4d)', 'cpt:87%',
                                  'agy5h:63%(17:30)wk:74%(4d)'):
                        self.assertIn(value, visible, (width, rows))
                    self.assertNotIn('haman', visible)

    async def test_all_values_survive_68_column_pane(self):
        await self.check_widths((68,))

    async def test_all_values_survive_narrow_pane(self):
        await self.check_widths((50,))

    async def test_values_survive_shrinking_and_growing_pane(self):
        await self.check_widths((140, 68, 50, 140))
