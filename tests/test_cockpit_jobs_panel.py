"""cockpit jobs_panel 模組測試：build_jobs_nodes 純資料 + JobsPanel widget 行為。"""
from __future__ import annotations

import unittest

try:
    from textual.app import App as _TextualApp, ComposeResult

    HAS_TEXTUAL = hasattr(_TextualApp, "run_test")
except Exception:  # pragma: no cover - textual not installed
    ComposeResult = None  # type: ignore
    HAS_TEXTUAL = False

from paulshaclaw.cockpit.jobs_panel import (
    JobsPanel,
    build_jobs_nodes,
    status_style,
)
from paulshaclaw.cockpit.models import JobGroup, JobRow


def row(slice_id, state="running", **kwargs):
    return JobRow(slice_id=slice_id, state=state, source_section=kwargs.pop("source_section", "in_flight"), **kwargs)


class BuildJobsNodesSingleTests(unittest.TestCase):
    """單 phase 群：一個頂層節點、無 children（除非 needs_human 帶 detail）。"""

    def test_single_slice_no_children(self):
        groups = (JobGroup(key="wf-abc", rows=(row("wf-abc-build"),)),)
        specs = build_jobs_nodes(groups)
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec.key, "wf-abc")
        self.assertEqual(spec.children, ())
        self.assertTrue(spec.expand, "群組層預設展開（#322）")
        plain = "".join(text for text, _ in spec.segments)
        self.assertIn("build", plain)

    def test_single_slice_needs_human_gets_detail_child(self):
        groups = (
            JobGroup(
                key="wf-abc",
                rows=(
                    row(
                        "wf-abc-build",
                        source_section="attention",
                        reason="等審核",
                        next_actions=("approve",),
                        needs_human=True,
                    ),
                ),
            ),
        )
        specs = build_jobs_nodes(groups)
        spec = specs[0]
        self.assertFalse(spec.expand, "單列 detail 預設收合，避免 10 行區被 detail 吃光")
        self.assertEqual(len(spec.children), 1)
        detail = spec.children[0]
        self.assertEqual(detail.key, "wf-abc/detail")
        self.assertEqual(detail.children, ())
        text, color = detail.segments[0]
        self.assertTrue(text.startswith("↳ "))
        self.assertIn("等審核", text)
        self.assertEqual(color, "#FBBF24")

    def test_single_slice_needs_human_without_reason_has_no_detail_child(self):
        # 單 slice 群的 group.detail_line 在缺 reason／next_actions 時刻意收斂為
        # ""（models.JobGroup.detail_line），不像 JobRow.detail_line 會退回一句
        # 「上游未帶...」——build_jobs_nodes 用的是 group.detail_line，所以這裡
        # 不掛 child，但 group 仍要展開（expand 只看 needs_human，不看有沒有 detail）。
        groups = (
            JobGroup(
                key="wf-xyz",
                rows=(row("wf-xyz-build", source_section="attention", needs_human=True),),
            ),
        )
        spec = build_jobs_nodes(groups)[0]
        self.assertTrue(spec.expand)
        self.assertEqual(spec.children, ())

    def test_not_needs_human_single_group_expands_no_child(self):
        # 群組層預設展開（#322）：即便非 needs_human 的單列群也要展開，让工作列可见；
        # 沒有 detail 子列，expand 僅是「已展開但無子節點」。
        not_needing = JobGroup(key="wf-ok", rows=(row("wf-ok-build"),))
        ok_spec = build_jobs_nodes((not_needing,))[0]
        self.assertTrue(ok_spec.expand)
        self.assertEqual(ok_spec.children, ())


class BuildJobsNodesMultiPhaseTests(unittest.TestCase):
    def _multi_group(self, second_needs_human=True):
        rows = (
            row("wf-abc-build", state="running"),
            row(
                "wf-abc-verification",
                state="blocked",
                source_section="attention",
                reason="等 CI",
                next_actions=("retry", "skip"),
                needs_human=second_needs_human,
            ),
        )
        return JobGroup(key="wf-abc", rows=rows)

    def test_multi_phase_one_child_per_slice(self):
        group = self._multi_group()
        specs = build_jobs_nodes((group,))
        spec = specs[0]
        self.assertEqual(spec.key, "wf-abc")
        self.assertTrue(spec.expand, "有人在等的多 phase 群要預設展開")
        self.assertEqual(len(spec.children), 2)
        build_child, verify_child = spec.children
        self.assertEqual(build_child.key, "wf-abc/wf-abc-build")
        self.assertEqual(verify_child.key, "wf-abc/wf-abc-verification")
        # phase 短名要把 group key 前綴剝掉。
        build_text = "".join(t for t, _ in build_child.segments)
        verify_text = "".join(t for t, _ in verify_child.segments)
        self.assertIn("build", build_text)
        self.assertNotIn("wf-abc-build", build_text)
        self.assertIn("verification", verify_text)

    def test_multi_phase_needs_human_child_gets_detail_grandchild(self):
        group = self._multi_group(second_needs_human=True)
        specs = build_jobs_nodes((group,))
        verify_child = specs[0].children[1]
        # detail 預設收合（#322）：detail 子列仍在，但預設不展開，需 enter/space 才展開。
        self.assertFalse(verify_child.expand)
        self.assertEqual(len(verify_child.children), 1)
        detail = verify_child.children[0]
        self.assertEqual(detail.key, "wf-abc/wf-abc-verification/detail")
        text, color = detail.segments[0]
        self.assertTrue(text.startswith("↳ "))
        self.assertIn("等 CI", text)
        self.assertEqual(color, "#FBBF24")

    def test_multi_phase_without_needs_human_no_detail(self):
        group = self._multi_group(second_needs_human=False)
        specs = build_jobs_nodes((group,))
        spec = specs[0]
        # 群組層預設展開（#322）：讓分 phase 行可見；detail 一律預設收合。
        self.assertTrue(spec.expand)
        for child in spec.children:
            self.assertEqual(child.children, ())
            self.assertFalse(child.expand)


class BuildJobsNodesKeyStabilityTests(unittest.TestCase):
    def test_keys_stable_across_identical_rebuilds(self):
        group = JobGroup(
            key="wf-abc",
            rows=(
                row("wf-abc-build"),
                row(
                    "wf-abc-verification",
                    source_section="attention",
                    reason="r",
                    next_actions=("a",),
                    needs_human=True,
                ),
            ),
        )
        specs_a = build_jobs_nodes((group,))
        specs_b = build_jobs_nodes((group,))

        def keys(specs):
            out = []
            for spec in specs:
                out.append(spec.key)
                out.extend(keys(spec.children))
            return out

        self.assertEqual(keys(specs_a), keys(specs_b))

    def test_multiple_groups_get_distinct_keys(self):
        groups = (
            JobGroup(key="wf-a", rows=(row("wf-a-build"),)),
            JobGroup(key="wf-b", rows=(row("wf-b-build"),)),
        )
        specs = build_jobs_nodes(groups)
        self.assertEqual([s.key for s in specs], ["wf-a", "wf-b"])


class BuildJobsNodesColorTests(unittest.TestCase):
    def test_status_style_five_buckets(self):
        """#308 owner 裁決：glyph 統一「•」，五桶顏色——wait-for-start 白、
        working 綠、broke 紅、wait-confirm 橘、finished 灰；未知退中性。"""
        # 白＝終端預設前景（#317）
        self.assertEqual(status_style("ready"), ("•", ""))
        self.assertEqual(status_style("blocked"), ("•", ""))
        self.assertEqual(status_style("running"), ("•", "#22C55E"))
        self.assertEqual(status_style("failed"), ("•", "#EF4444"))
        self.assertEqual(status_style("needs_human"), ("•", "#F97316"))
        self.assertEqual(status_style("attention"), ("•", "#F97316"))
        self.assertEqual(status_style("passed"), ("•", "#94A3B8"))
        self.assertEqual(status_style("workflow-tracked"), ("•", "#94A3B8"))
        self.assertEqual(status_style("exited"), ("•", "#94A3B8"))
        # 未知狀態退更暗的中性色，不與 finished 撞色（#311）。
        glyph, color = status_style("mystery-state")
        self.assertEqual(glyph, "•")
        self.assertEqual(color, "#64748B")

    def test_running_uses_status_style_color(self):
        groups = (JobGroup(key="wf-abc", rows=(row("wf-abc-build", state="running"),)),)
        spec = build_jobs_nodes(groups)[0]
        glyph, color = status_style("running")
        first_text, first_color = spec.segments[0]
        self.assertEqual(first_color, color)
        self.assertIn(glyph, first_text)

    def test_needs_human_group_uses_attention_color_even_with_other_raw_state(self):
        # 多 phase 群整體上色走 needs_human -> attention 規則，不管領頭 slice 的 state。
        groups = (
            JobGroup(
                key="wf-abc",
                rows=(
                    row("wf-abc-build", state="running"),
                    row(
                        "wf-abc-verification",
                        state="some_weird_state",
                        source_section="attention",
                        reason="r",
                        needs_human=True,
                    ),
                ),
            ),
        )
        spec = build_jobs_nodes(groups)[0]
        _, attention_color = status_style("attention")
        _, first_color = spec.segments[0]
        self.assertEqual(first_color, attention_color)

    def test_phase_child_needs_human_uses_attention_color_regardless_of_raw_state(self):
        groups = (
            JobGroup(
                key="wf-abc",
                rows=(
                    row("wf-abc-build", state="running"),
                    row(
                        "wf-abc-verification",
                        state="some_weird_state",
                        source_section="attention",
                        reason="r",
                        needs_human=True,
                    ),
                ),
            ),
        )
        verify_child = build_jobs_nodes(groups)[0].children[1]
        _, attention_color = status_style("needs_human")
        _, child_color = verify_child.segments[0]
        self.assertEqual(child_color, attention_color)


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class JobsPanelWidgetTests(unittest.IsolatedAsyncioTestCase):
    class _HostApp(_TextualApp):
        def compose(self) -> "ComposeResult":
            yield JobsPanel(id="global-jobs")

    def _groups(self, second_needs_human=True):
        rows = (
            row("wf-abc-build", state="running"),
            row(
                "wf-abc-verification",
                state="blocked",
                source_section="attention",
                reason="等 CI",
                next_actions=("retry",),
                needs_human=second_needs_human,
            ),
        )
        return (JobGroup(key="wf-abc", rows=rows),)

    async def test_set_groups_builds_expected_node_structure(self):
        app = self._HostApp()
        async with app.run_test(size=(100, 40)) as pilot:
            panel = app.query_one("#global-jobs", JobsPanel)
            panel.set_groups(self._groups())
            await pilot.pause()
            self.assertEqual(len(panel.root.children), 1)
            group_node = panel.root.children[0]
            self.assertEqual(group_node.data, "wf-abc")
            self.assertTrue(group_node.is_expanded)
            self.assertEqual(len(group_node.children), 2)
            build_node, verify_node = group_node.children
            self.assertEqual(build_node.data, "wf-abc/wf-abc-build")
            self.assertEqual(verify_node.data, "wf-abc/wf-abc-verification")
            # detail 預設收合（#322）：detail 子列仍在，但預設不展開。
            self.assertFalse(verify_node.is_expanded)
            self.assertEqual(len(verify_node.children), 1)
            self.assertEqual(verify_node.children[0].data, "wf-abc/wf-abc-verification/detail")

    async def test_manual_collapse_survives_next_set_groups(self):
        app = self._HostApp()
        async with app.run_test(size=(100, 40)) as pilot:
            panel = app.query_one("#global-jobs", JobsPanel)
            panel.set_groups(self._groups())
            await pilot.pause()
            group_node = panel.root.children[0]
            # 使用者手動收合（走 node.collapse()，會 post NodeCollapsed）。
            group_node.collapse()
            await pilot.pause()
            self.assertFalse(panel.root.children[0].is_expanded)

            # 換一批「內容不同」的 groups（否則純文字投影相同會直接跳過重建），
            # 驗證使用者的手動收合仍蓋過 spec 預設的 expand=True。
            # 注意 _groups() 預設就是 needs_human=True——changed 批必須用 False
            # 才會改變投影、真正觸發重建（否則本測試恆真）。
            collapsed_node = panel.root.children[0]
            changed = self._groups(second_needs_human=False)
            panel.set_groups(changed)
            await pilot.pause()
            panel.set_groups(self._groups())
            await pilot.pause()
            # 先驗重建真的發生（節點是新物件），再驗同 key 的手動收合仍保留。
            self.assertIsNot(panel.root.children[0], collapsed_node)
            self.assertFalse(panel.root.children[0].is_expanded)

    async def test_cursor_position_preserved_across_rebuild(self):
        app = self._HostApp()
        async with app.run_test(size=(100, 40)) as pilot:
            panel = app.query_one("#global-jobs", JobsPanel)
            panel.set_groups(self._groups())
            await pilot.pause()
            group_node = panel.root.children[0]
            verify_node = group_node.children[1]
            panel.select_node(verify_node)
            await pilot.pause()
            self.assertEqual(panel.cursor_node.data, "wf-abc/wf-abc-verification")

            # 換一批內容不同（多一群）但同一個 key 仍存在的 groups，觸發真正的重建。
            more_groups = self._groups() + (
                JobGroup(key="wf-zzz", rows=(row("wf-zzz-build"),)),
            )
            panel.set_groups(more_groups)
            await pilot.pause()
            self.assertEqual(panel.cursor_node.data, "wf-abc/wf-abc-verification")

    async def test_set_message_shows_single_leaf(self):
        app = self._HostApp()
        async with app.run_test(size=(100, 40)) as pilot:
            panel = app.query_one("#global-jobs", JobsPanel)
            panel.set_groups(self._groups())
            await pilot.pause()
            panel.set_message("degraded: manager offline", "#FBBF24")
            await pilot.pause()
            self.assertEqual(len(panel.root.children), 1)
            self.assertEqual(panel.root.children[0].data, "__message__")

    async def test_no_rebuild_when_projection_unchanged(self):
        app = self._HostApp()
        async with app.run_test(size=(100, 40)) as pilot:
            panel = app.query_one("#global-jobs", JobsPanel)
            groups = self._groups()
            panel.set_groups(groups)
            await pilot.pause()
            group_node_before = panel.root.children[0]

            # 同樣內容的第二批 JobGroup（新物件，但文字投影相同）不應觸發重建：
            # 節點物件應維持同一份（同一性比較），避免不必要的閃爍與 cursor 抖動。
            same_groups = self._groups()
            panel.set_groups(same_groups)
            await pilot.pause()
            group_node_after = panel.root.children[0]
            self.assertIs(group_node_before, group_node_after)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
