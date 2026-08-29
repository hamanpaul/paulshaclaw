"""#322 JOBS 三軸重設計回歸測試。

涵蓋計畫驗證段列出的七類行為（紅→綠，鎖定已實作契約，防止日後 regress）：

1. ``slices_from_status`` 收受 workflow_run slice（帶 kind/work_id/current_phase）
   原封不散——42 個收成 42 列 JobRows（核心 regression）。
2. ``kind: "slice"`` 舊行為不變。
3. ``not_claimable`` 含進 phase "未認領"；上游缺該 key 時不崩潰（0.1.8 相容）。
4. ``persona`` 屬性對應 cortex ``validate_manager_spine``（7 phase，與 cortex
   契约一致）。
5. 三軸分組鍵與群組排序（needs_human 優先、未認領／待認積壓沉底）。
6. ``g`` 鍵循環三軸（Pilot）＋換軸把 axis threaded 到渲染。
7. 4 欄軸排版（宽度 80、CJK 不崩潰）。
"""

from types import SimpleNamespace

import unittest

import paulshaclaw.cockpit.app as cockpit_app

try:
    from textual.pilot import Pilot
    from textual.app import App as _TextualApp
    HAS_TEXTUAL = hasattr(_TextualApp, "run_test")
except Exception:  # pragma: no cover
    Pilot = None
    HAS_TEXTUAL = False

from paulshaclaw.cockpit.app import (
    CockpitApp,
    group_job_rows,
    jobs_counts_summary,
    slices_from_status,
)
from paulshaclaw.cockpit.jobs_panel import (
    _axis_layout_columns,
    _display_width,
    _ellipsize_middle,
    _pad_display,
    _row_work_id,
    build_jobs_nodes,
)
from paulshaclaw.cockpit.models import JobRow, JobGroup, _PHASE_TO_PERSONA, PaneRecord
from paulshaclaw.cockpit.actions import LayoutActionService


def pane_record(
    pane_id: str,
    *,
    session_name: str = "main",
    title: str = "pane",
    command: str = "bash",
    left: int = 0,
    top: int = 0,
    width: int = 80,
    height: int = 24,
) -> PaneRecord:
    """Test-only PaneRecord 建構子（與 test_stage11 的 pane_record 同義）。"""
    return PaneRecord(
        pane_id=pane_id,
        session_name=session_name,
        window_index="0",
        title=title,
        command=command,
        left=left,
        top=top,
        width=width,
        height=height,
        active=False,
    )


def jrow(slice_id: str, *, phase: str, source_section: str = "in_flight",
         repo: str = "", work_id: str = "", needs_human: bool = False) -> JobRow:
    """精簡 JobRow 建構子：phase 驅動 persona／is_in_line／is_pending_claim／
    is_not_claimable 所有三軸屬性；source_section 控制 _group_rank 的 in_flight；
    needs_human 控制「等人」優先（attention 列要設 True）；work_id＋phase 皆設才
    是三軸行（`_row_is_axis`），走四欄語意化排版。"""
    return JobRow(
        slice_id=slice_id,
        state=phase,
        source_section=source_section,
        phase=phase,
        repo=repo,
        work_id=work_id,
        needs_human=needs_human,
    )


def _flatten_node_text(node) -> str:
    """把單一節點（含子節點）攤成純文字，供內容斷言用。"""
    text = "".join(segment_text for segment_text, _ in node.segments)
    for child in node.children:
        text += "\n" + _flatten_node_text(child)
    return text


# --- 1. ingest：workflow_run / slice / not_claimable --------------------

class JobIngestTests(unittest.TestCase):
    def test_42_workflow_run_rows_survive_ingest(self) -> None:
        """一個 manager deck 常同時有數十個 workflow，每個 phase 各一列。
        實測 42 個 workflow_run（無 slice_id）全收成 42 列 JobRows，不得減半。"""
        status = {"in_flight": []}
        for wf in range(1, 22):  # 21 workflows × 2 phases = 42
            status["in_flight"].append(
                {
                    "kind": "workflow_run",
                    "work_id": f"wf-{wf:04d}-build",
                    "current_phase": "build",
                    "run_id": f"run-{wf}",
                }
            )
            status["in_flight"].append(
                {
                    "kind": "workflow_run",
                    "work_id": f"wf-{wf:04d}-verify",
                    "current_phase": "verify",
                    "run_id": f"run-{wf}",
                }
            )
        rows = slices_from_status(status)

        self.assertEqual(len(rows), 42)
        self.assertTrue(all(isinstance(r, JobRow) for r in rows))
        # workflow_run：帶 kind、phase 取 current_phase、work_id 自 work_id 欄。
        self.assertTrue(all(r.kind == "workflow_run" for r in rows))
        self.assertTrue(all(r.phase in {"build", "verify"} for r in rows))
        self.assertTrue(all(r.work_id.startswith("wf-") for r in rows))

    def test_kind_slice_unchanged(self) -> None:
        """kind: slice 仍走 legacy 路徑（phase 由 slice_id 尾段推，work_id 為整串）。"""
        rows = slices_from_status(
            {
                "ready": ["fix-dispatch-98-build"],
                "held": [{"slice_id": "fix-dispatch-98-code-review", "reasons": ["x"]}],
            }
        )
        groups = group_job_rows(rows)
        self.assertEqual([g.key for g in groups], ["fix-dispatch-98"])
        self.assertEqual(len(groups[0].rows), 2)
        self.assertTrue(all(not r.work_id.startswith("wf-") for r in rows))

    def test_not_claimable_rows_and_missing_key_safe(self) -> None:
        """0.1.8 cortex 沒有 not_claimable key：status 有該 key 收成 6 列 phase
        "未認領"；完全沒該 key 時（legacy 安裝版）不崩潰、0 列。"""
        status = {
            "not_claimable": [
                {"work_id": f"unclaimed-{i}", "detail": "missing_issue"} for i in range(6)
            ]
        }
        rows = slices_from_status(status)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r.phase == "未認領" for r in rows))
        self.assertTrue(all(r.is_not_claimable for r in rows))

        # 無 key：0 列，不崩潰（slices_from_status 回傳空 tuple）。
        self.assertFalse(slices_from_status({"in_flight": []}))

    def test_group_summary_trailer_only_includes_nonzero_segments(self) -> None:
        """#322 回溯：summary_trailer 只印非零區段。純未認領群只印「不可認領」、
        不含「在管線／待認領」；混合群（在管線＋待認領＋未認領）三段皆印。"""
        # 纯未認領：is_not_claimable 全 2，在管線／待認領皆 0。
        unclaimed = JobGroup("g1", (jrow("u1", phase="未認領"), jrow("u2", phase="未認領")))
        self.assertEqual(unclaimed.not_claimable_count, 2)
        self.assertEqual(unclaimed.in_line_count, 0)
        self.assertEqual(unclaimed.pending_claim_count, 0)
        self.assertEqual(unclaimed.summary_trailer, "2 件 · 2 不可認領")
        self.assertNotIn("在管線", unclaimed.summary_trailer)
        self.assertNotIn("待認領", unclaimed.summary_trailer)

        # 混合：在管線（build）＋待認領（claim）＋未認領。三段皆非零。
        mix = JobGroup(
            "g2",
            (
                jrow("b1", phase="build", source_section="in_flight", repo="r", work_id="wf-x-build"),
                jrow("c1", phase="claim", source_section="in_flight"),
                jrow("u3", phase="未認領", source_section="in_flight"),
            ),
        )
        self.assertEqual(mix.in_line_count, 1)
        self.assertEqual(mix.pending_claim_count, 1)
        self.assertEqual(mix.not_claimable_count, 1)
        self.assertEqual(mix.summary_trailer, "3 件 · 1 在管線 · 1 待認領 · 1 不可認領")


# --- 4. persona 屬性對應 cortex validate_manager_spine -------------------

class JobPersonaTests(unittest.TestCase):
    def test_persona_agrees_with_cortex_validate_manager_spine(self) -> None:
        """persona 映射必须与 cortex WorkflowManifest.validate_manager_spine 的
        实际执行一致：用 cockpit 的 _PHASE_TO_PERSONA 产出每 phase 的 persona 建构
        完整 manifest，cortex 须接受（契约）；把任一 persona 改错，cortex 须拒绝。
        這是真·雙向交叉驗證，非 cockpit 端自證自答。"""
        from paulsha_cortex.coordinator.workflow import (
            WORKFLOW_MANIFEST_VERSION,
            WORKFLOW_PHASES,
            WorkflowManifest,
        )
        manifest = {
            "version": WORKFLOW_MANIFEST_VERSION,
            "combo": "test-combo",
            "task_slug": "test-task",
            "steps": [
                {
                    "phase": phase,
                    "persona": _PHASE_TO_PERSONA[phase],  # cockpit 的契约
                    "card": f"{phase}-card",
                    "executor": None,
                    "model": None,
                    "domain": None,
                    "inputs": [],
                    "outputs": [],
                    "gate_result": "passed",
                }
                for phase in WORKFLOW_PHASES
            ],
        }
        # cockpit 产出的 persona 须被 cortex 接受（不抛 ValueError）。
        WorkflowManifest.from_dict(manifest).validate_manager_spine()

        # 把 build step 的 persona 改错（→ manager），cortex 须拒绝。
        manifest["steps"][WORKFLOW_PHASES.index("build")]["persona"] = "manager"
        with self.assertRaises(ValueError):
            WorkflowManifest.from_dict(manifest).validate_manager_spine()

        # cockpit persona 属性逐 phase 与契约一致。
        for phase in WORKFLOW_PHASES:
            self.assertEqual(jrow(phase, phase=phase).persona, _PHASE_TO_PERSONA[phase])

    def test_persona_unknown_and_unclaimed_default_empty(self) -> None:
        """未認領與未知 phase（含 legacy slice 無 phase）退回空字串。"""
        self.assertEqual(jrow("x", phase="未認領").persona, "")
        self.assertEqual(jrow("x", phase="unknown").persona, "")


# --- 5. 三軸分組鍵與群組排序 --------------------------------------------

class JobAxisGroupingTests(unittest.TestCase):
    def test_project_axis_groups_by_repo_project(self) -> None:
        rows = (
            jrow("task-a", phase="build", repo="hamanpaul/paulsha-cortex"),
            jrow("task-b", phase="build", repo="hamanpaul/paulsha-cortex"),
            jrow("task-c", phase="verify", repo="hamanpaul/paulsha-hippo"),
        )
        groups = group_job_rows(rows, axis="project")
        keys = [g.key for g in groups]
        self.assertEqual(len(keys), 2)
        self.assertIn("paulsha-cortex", keys)
        self.assertIn("paulsha-hippo", keys)

    def test_stage_axis_groups_by_phase(self) -> None:
        rows = (
            jrow("a", phase="build"),
            jrow("b", phase="verify"),
            jrow("c", phase="verify"),
        )
        self.assertEqual([g.key for g in group_job_rows(rows, axis="stage")], ["build", "verify"])

    def test_agent_axis_groups_by_persona(self) -> None:
        rows = (
            jrow("a", phase="build"),  # builder
            jrow("b", phase="verify"),  # reviewer
            jrow("c", phase="verify"),  # reviewer
        )
        self.assertEqual([g.key for g in group_job_rows(rows, axis="agent")], ["builder", "reviewer"])

    def test_needs_human_priority_preserved_per_axis(self) -> None:
        """每軸都保留 needs_human 優先：等人的群排最前，不因換軸而掉到末尾。"""
        rows = (
            jrow("ready-a", phase="ready"),
            jrow("attn-a", phase="attention", source_section="attention", needs_human=True),
            jrow("ready-b", phase="ready"),
        )
        for axis in ("project", "stage", "agent"):
            groups = group_job_rows(rows, axis=axis)
            first = groups[0]
            # needs_human 優先：頭群需有人等；attn-a 在頭群內。
            self.assertTrue(first.needs_human, f"axis={axis} 頭群應 needs_human")
            self.assertIn("attn-a", [r.slice_id for r in first.rows])

    def test_unclaimed_and_pending_claim_sink(self) -> None:
        """未認領（未認領 phase）與待認積壓（claim phase）沉底；真正在管線的
        （build/verify/…）排前面。source_section=in_flight 讓 build 在管線排前。"""
        rows = (
            jrow("p1", phase="claim", source_section="in_flight"),
            jrow("u1", phase="未認領", source_section="in_flight"),
            jrow("b1", phase="build", source_section="in_flight"),
        )
        ordered = [g.key for g in group_job_rows(rows, axis="stage")]
        self.assertEqual(ordered[0], "build")
        self.assertEqual(set(ordered[1:]), {"claim", "未認領"})

    def test_grouping_default_axis_is_project(self) -> None:
        """group_job_rows 預設軸為 project（不傳 axis 時）。"""
        rows = (jrow("a", phase="build", repo="hamanpaul/paulsha-cortex"),)
        groups = group_job_rows(rows)
        self.assertEqual(groups[0].key, "paulsha-cortex")


# --- jobs_counts_summary -------------------------------------------------

class JobCountsSummaryTests(unittest.TestCase):
    def test_summary_only_nonzero_segments(self) -> None:
        rows = (
            jrow("a", phase="build"),  # in_line
            jrow("b", phase="claim", source_section="in_flight"),  # 待認積壓
            jrow("c", phase="未認領"),  # 不可認領
            jrow("d", phase="verify"),  # in_line
        )
        # 4 行：2 in_line、1 pending、1 unclaimed。
        self.assertEqual(
            jobs_counts_summary(rows),
            "4 件 · 2 在管線 · 1 待認領 · 1 不可認領",
        )

    def test_summary_zero_in_line_only_counts_head(self) -> None:
        # 全未認領：不在管線也不待認領，只出「不可認領」。
        rows = (jrow("u1", phase="未認領"), jrow("u2", phase="未認領"))
        self.assertEqual(jobs_counts_summary(rows), "2 件 · 2 不可認領")


# --- 7. 4 欄軸排版 -------------------------------------------------------

class JobAxisRenderingTests(unittest.TestCase):
    def test_axis_single_row_has_four_segments(self) -> None:
        """workflow_run 行（帶 work_id＋phase）在 project 軸上切成 4 欄
        （glyph · phase · work_id · persona），宽度 80 仍滿 4 欄。project 軸的
        第 1 欄為 phase、第 3 欄為 persona（project 是群組頭身分，非行內欄）。"""
        rows = (jrow("task-xyz", phase="build", repo="hamanpaul/paulsha-cortex",
                      work_id="wf-abc123-build"),)
        (group,) = group_job_rows(rows, axis="project")
        nodes = build_jobs_nodes([group], 80, axis="project")
        root = nodes[0]
        self.assertEqual(len(root.segments), 4)            # 4 欄語意化
        rendered = _flatten_node_text(root)
        self.assertIn("build", rendered)                   # col1 = phase（project 軸）
        self.assertIn("wf-abc123-build", rendered)         # work_id 欄
        self.assertIn("builder", rendered)                 # col3 = persona（project 軸）
        self.assertEqual(group.key, "paulsha-cortex")      # project 軸按 repo 分群

    def test_axis_layout_cjk_aligned_does_not_crash(self) -> None:
        """4 欄內 CJK 字元採全角計寬，渲染不崩潰、宽度预算不因错位。"""
        rows = (jrow("task-中文-build", phase="build", repo="hamanpaul/中文專案",
                      work_id="wf-中文-build"),)
        (group,) = group_job_rows(rows, axis="project")
        nodes = build_jobs_nodes([group], 80, axis="project")
        self.assertEqual(len(nodes[0].segments), 4)
        self.assertIn("中文專案", group.key)  # CJK repo 正確分群


# --- 6. Pilot：g 鍵循環三軸 ----------------------------------------------

@unittest.skipUnless(HAS_TEXTUAL, "requires textual with run_test support")
class JobAxisPilotTests(unittest.IsolatedAsyncioTestCase):
    STATUS = {"in_flight": [{"kind": "workflow_run", "work_id": "wf-1-build", "current_phase": "build"}]}

    def _app(self) -> CockpitApp:
        panes = (
            pane_record("%0", title="cockpit", command="python", width=120, height=40),
            pane_record("%1", title="agent1", command="node", top=40, width=60, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={"%1": ()},
            actions=LayoutActionService(),
        )
        app.manager_client = SimpleNamespace(read_status=lambda: self.STATUS)
        return app

    def _widget(self, app: CockpitApp):
        from paulshaclaw.cockpit.jobs_panel import JobsPanel
        return app.query_one("#global-jobs", JobsPanel)

    async def test_g_key_cycles_three_axes(self) -> None:
        app = self._app()

        async with app.run_test() as pilot:
            self.assertEqual(app._jobs_axis, "project")  # 預設軸
            axes = [app._jobs_axis]
            for _ in range(3):
                await pilot.press("g")
                axes.append(app._jobs_axis)
            self.assertEqual(axes, ["project", "stage", "agent", "project"])

    async def test_set_groups_receives_current_axis_each_press(self) -> None:
        """換軸時面板 set_groups 收到對應軸（widget._last_axis）——驗證轴切到
        渲染管线，不只 app state 變。"""
        app = self._app()

        async with app.run_test() as pilot:
            for expected in ("stage", "agent"):
                await pilot.press("g")
                self.assertEqual(app._jobs_axis, expected)
                self.assertEqual(self._widget(app)._last_axis, expected)

    async def test_jobs_panel_not_flattened_height_bounded(self) -> None:
        """#322 regress: JOBS 面板曾被压扁成 3 行。
        Cockpit 由 Static 換成 Tree 後，CSS `#global-jobs { height: auto }` 在
        縱向 Stack 裡自然高度只收斂到 3，又被 `#work-list { height: 1fr }` 擠扁。
        修法：`height: 12`（bounded）＋ App 層收合時把 `max_height` 設 3 蓋過。
        此測試鎖定：展開時面板 ≥ 12（非 3），收合時可被蓋為 3。"""
        app = self._app()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            jj = self._widget(app)
            # 展開：固定高度 12（bounded），不再是扁到 3
            self.assertEqual(jj._size.height, 12)
            # 收合：App 層 max_height=3 蓋過此值
            jj.styles.max_height = 3
            await pilot.pause()
            self.assertEqual(jj._size.height, 3)

    async def test_per_axis_expanded_state_isolated(self) -> None:
        """每軸各有自己的 _user_expanded（keyed by axis→key→bool）；換軸不混。"""
        app = self._app()

        async with app.run_test() as pilot:
            await pilot.press("g")  # stage
            await pilot.press("g")  # agent
            await pilot.press("g")  # 回到 project
            widget = self._widget(app)
            self.assertEqual(app._jobs_axis, "project")
            self.assertEqual(set(widget._user_expanded), {"project", "stage", "agent"})


# --- 8. review #322 regression：workflow_run 路由／stage 軸列／群內排序 ----------

class JobReviewRegressionTests(unittest.TestCase):
    """Codex luna review #322 的 FAIL findings 修复回归。锁定修复后的契约，
    防止日后回归：workflow_run 行（work_id 以 wf- 開頭）须走軸分組、stage 軸
    三欄须为 work_id·persona·repo、群內 claim 须沉底於在管線行之後。"""

    def _status(self, entries) -> dict:
        return {"in_flight": entries, "degraded": False}

    def _wf_run(self, work_id, phase, repo="hamanpaul/paulsha-cortex") -> dict:
        return {
            "kind": "workflow_run",
            "work_id": work_id,
            "current_phase": phase,
            "run_id": f"run-{work_id}",
            "repo": repo,
        }

    def test_review_cleanup_removes_legacy_string_guessing_api_remnants(self) -> None:
        """review #322 指出的收尾：舊的 workflow_id／_phase_label／_PHASE_SUFFIXES
        不再外漏於目前的模型／分組 API；legacy 相容由內聚 helper 處理。"""
        self.assertFalse(hasattr(JobRow, "workflow_id"))
        self.assertFalse(hasattr(JobGroup, "workflow_id"))
        self.assertFalse(hasattr(JobGroup, "_phase_label"))
        self.assertFalse(hasattr(cockpit_app, "_PHASE_SUFFIXES"))
        self.assertFalse(hasattr(cockpit_app, "_group_key"))

    def test_workflow_run_work_id_starting_wf_routes_by_axis_not_hash(self) -> None:
        """#1（ingest）回归：work_id 以 wf- 開頭的 workflow_run 行（如 wf-0001-build），
        三軸分組须走 _axis_key——stage 軸收成 phase、agent 軸收成 persona，
        不得被 legacy slice-id 相容路徑收成工作流前缀群。"""
        rows = slices_from_status(
            self._status(
                [
                    self._wf_run("wf-0001-build", "build"),
                    self._wf_run("wf-0002-verify", "verify"),
                    self._wf_run("wf-0003-verify", "verify"),
                ]
            )
        )
        self.assertEqual(len(rows), 3)
        # stage 軸：build／verify 兩群（非 wf-0001 之类前缀群）。
        self.assertEqual([g.key for g in group_job_rows(rows, axis="stage")], ["build", "verify"])
        # agent 軸：builder／reviewer。
        self.assertEqual([g.key for g in group_job_rows(rows, axis="agent")], ["builder", "reviewer"])
        # project 軸按 repo 收群（不因 wf- 前缀拆群）。
        self.assertEqual([g.key for g in group_job_rows(rows, axis="project")], ["paulsha-cortex"])

    def test_dedup_keeps_cross_repo_same_work_id(self) -> None:
        """#4（dedup）回归：不同 repo 同名 work_id 的 workflow_run 不互相吃彼此——
        用 (repo, work_id) 复合身分去重，跨 repo 同名各列。"""
        rows = slices_from_status(
            self._status(
                [
                    self._wf_run("wf-0001-build", "build", repo="hamanpaul/paulsha-cortex"),
                    self._wf_run("wf-0001-build", "build", repo="hamanpaul/paulsha-hippo"),
                ]
            )
        )
        # 两笔不同 repo，不去重，各列。
        self.assertEqual(len(rows), 2)
        projects = {r.project for r in rows}
        self.assertEqual(projects, {"paulsha-cortex", "paulsha-hippo"})

    def test_group_rows_sorted_claim_sinks_below_in_line(self) -> None:
        """#2（sort）回归：同一群內，claim（待認積壓）行排在 build／verify（在管線）
        之後，不反序。"""
        rows = (
            jrow("wf-abc-claim", phase="claim", source_section="in_flight"),
            jrow("wf-abc-build", phase="build", source_section="in_flight"),
            jrow("wf-abc-verify", phase="verify", source_section="in_flight"),
        )
        (group,) = group_job_rows(rows, axis="project")  # 同一 wf-abc 群
        phases = [r.phase for r in group.rows]
        self.assertEqual(phases, ["build", "verify", "claim"])

    def test_project_axis_recent_done_workflow_rows_stay_in_repo_group(self) -> None:
        """#322 regression：project 軸下的 recent_done 不得因 wf-* slice_id 拆成
        獨立 workflow 群；它要歸到 repo 群底下，才不會佔掉預設視野。"""
        rows = slices_from_status(
            {
                "degraded": False,
                "in_flight": [self._wf_run("wf-live-build", "build")],
                "recent_done": [
                    {
                        "slice_id": "wf-done-verification",
                        "gate_status": "passed",
                        "workflow_repo": "hamanpaul/paulsha-cortex",
                    }
                ],
            }
        )

        groups = group_job_rows(rows, axis="project")

        self.assertEqual([g.key for g in groups], ["paulsha-cortex"])
        self.assertEqual(
            [(row.slice_id, row.source_section) for row in groups[0].rows],
            [("wf-live-build", "in_flight"), ("wf-done-verification", "recent_done")],
        )

    def test_stage_axis_columns_show_work_id_persona_repo(self) -> None:
        """#6（jobs_panel）回归：stage 軸三欄是 work_id·persona·repo（非
        work_id·work_id·？），且带 persona——project／agent 轴才显示 persona 的误区
        不再发生。"""
        rows = slices_from_status(
            self._status([self._wf_run("wf-1-build", "build")])
        )
        (group,) = group_job_rows(rows, axis="stage")
        nodes = build_jobs_nodes([group], 80, axis="stage")
        rendered = _flatten_node_text(nodes[0])
        self.assertIn("wf-1-build", rendered)         # col1 = work_id
        self.assertIn("builder", rendered)            # col2 = persona（stage 軸特有）
        self.assertIn("paulsha-cortex", rendered)     # col3 = repo

    def test_render_axis_row_ellipsizes_long_work_id(self) -> None:
        """#9（jobs_panel）回溯：工作識別欄（project／agent 軸的第 2 欄 work_id）超過
        column 寬時由 _ellipsize_middle 處理，不超出寬度預算——長 work_id 以「…」
        省略中段，不撐破 @80 版面。"""
        rows = (jrow("x", phase="build", repo="hamanpaul/paulsha-cortex",
                     work_id="wf-" + "a" * 100),)
        groups = group_job_rows(rows, axis="project")
        first_col, work_col, third_col = _axis_layout_columns(groups, 80, "project")
        raw = _row_work_id(rows[0])
        c2 = _pad_display(_ellipsize_middle(raw, work_col), work_col)
        # work_id 远宽于预算 → 触发省略，且显示宽度不超过 work_col（不超宽、不崩溃）。
        self.assertLessEqual(_display_width(c2), work_col)
        self.assertIn("…", c2)


if __name__ == "__main__":
    unittest.main()
