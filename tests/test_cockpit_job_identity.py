"""Consume Cortex's real identity contract without deriving identity from persona."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from paulshaclaw.cockpit.app import group_job_rows, slices_from_status
from paulshaclaw.cockpit.jobs_panel import JobsPanel, build_jobs_nodes


FIXTURE = Path(__file__).parent / "fixtures/workflow-execution-identity-828-status.json"


def plain(node) -> str:
    return "".join(text for text, _ in node.segments)


def all_text(nodes) -> str:
    return "\n".join(plain(node) + "\n" + all_text(node.children) for node in nodes)


def workflow():
    return dict(
        kind="workflow_run", work_id="example-work", run_id="workflow-example",
        repo="example/cortex", current_phase="build", gate_state="failed",
        reason="review failed", next_actions=["retry-build"], executor="codex",
        model="gpt-test", job_id="job-current", card="build-primary",
        identity_source="in-flight", execution_state="running",
    )


def test_producer_fixture_identity_survives_all_status_sections():
    # Losing an additive field in either the legacy or workflow ingest drops
    # identity from the actual producer payload, not only synthetic new rows.
    rows = slices_from_status(json.loads(FIXTURE.read_text()))
    by_key = {row.work_id or row.slice_id: row for row in rows}
    expected = {
        "workflow-828-retry-build-primary": ("codex", "gpt-5.3-codex", "in-flight", "running"),
        "example-work-retry": ("codex", "gpt-5.3-codex", "in-flight", "running"),
        "example-work-last": ("claude", "claude-sonnet-4.5", "last-execution", "exited"),
        "example-work-planned": ("cortex-manager", "deterministic", "planned", "not-dispatched"),
        "example-work-unknown": ("", "", "unknown", "not-dispatched"),
        "workflow-828-completed-build-primary": ("claude", "claude-sonnet-4.5", "last-execution", "exited"),
    }
    assert len(rows) == len(expected)
    for key, identity in expected.items():
        row = by_key[key]
        assert (row.executor, row.model, row.identity_source, row.execution_state) == identity
        assert row.card
    assert by_key["example-work-retry"].job_id == "job-828-retry"


@pytest.mark.parametrize("axis", ["project", "stage", "agent"])
def test_identity_details_distinguish_actual_last_planned_and_unknown(axis):
    rows = slices_from_status(json.loads(FIXTURE.read_text()))
    text = all_text(build_jobs_nodes(group_job_rows(rows, axis=axis), width=48, axis=axis))
    assert "執行中 · codex · gpt-5.3-codex" in text
    assert "上次執行 · claude · claude-sonnet-4.5" in text
    assert "預定／未派工 · cortex-manager · deterministic" in text
    assert "未派工 · executor 未提供 · model 未提供" in text
    assert "job-828-last" in text
    assert "build-primary" in text
    assert "retry-build" in text
    assert "workflow-828-last" in text


@pytest.mark.parametrize("bad", [None, 123, [], {}, False, "  "])
def test_malformed_identity_uses_typed_defaults_without_persona_guess(bad):
    item = workflow()
    for field in ("executor", "model", "job_id", "card", "identity_source", "execution_state"):
        item[field] = bad
    rows = slices_from_status({"attention": [item]})
    text = all_text(build_jobs_nodes(group_job_rows(rows)))
    assert "身份未提供 · executor 未提供 · model 未提供" in text
    assert "codex" not in text
    assert "gpt-test" not in text
    assert "builder" in text  # Role remains distinct from identity.


def test_old_workflow_and_unclaimed_identity_remain_readable():
    rows = slices_from_status({
        "attention": [{"kind": "workflow_run", "work_id": "old", "current_phase": "review"}],
        "not_claimable": [{"work_id": "new", "repo": "example/repo"}],
    })
    text = all_text(build_jobs_nodes(group_job_rows(rows)))
    assert "身份未提供 · executor 未提供 · model 未提供" in text
    assert "未派工 · executor 未提供 · model 未提供" in text


def test_unknown_source_does_not_promote_manifest_job_id_to_actual_identity():
    item = workflow()
    item["identity_source"] = "unknown"
    item["execution_state"] = "not-dispatched"
    text = all_text(build_jobs_nodes(group_job_rows(slices_from_status({"attention": [item]}))))
    assert "未派工 · executor 未提供 · model 未提供" in text
    assert "codex" not in text
    assert "gpt-test" not in text


def test_installed_producer_selects_retry_current_card_and_consumer_tracks_transition(tmp_path):
    from paulsha_cortex.coordinator import manager, manager_daemon
    from paulsha_cortex.coordinator.registry import JobRegistry
    from paulsha_cortex.coordinator.workflow import WorkflowStep

    registry = JobRegistry(state_path=tmp_path / "jobs.json")
    run = registry._manager_create_workflow_run(
        work_id="example-work", repo="example/repo", claim_key="example/repo/work/1",
        source_revision="a" * 64, workspace_root=str(tmp_path / "workspace"),
        combo="feature-oneshot", current_phase="build", attempts={"build": 1},
        steps=tuple(WorkflowStep(
            phase="build", persona="builder", card=card, executor=None, model=None,
            domain="test", inputs=(), outputs=(), gate_result=result,
        ) for card, result in [("setup", "passed"), ("build-primary", "pending")]),
    )

    def job(card, executor, model, *, repo="example/repo", phase="build", status="running"):
        value = registry.create_job(
            task=f"{run.run_id}-{card}-{executor}", persona="builder", branch="feature/example",
            pane="", worktree=str(tmp_path / "worktree"), executor=executor, model_id=model,
            workflow_run_id=run.run_id, workflow_claim_key=run.claim_key,
            workflow_repo=repo, workflow_card=card, workflow_phase=phase,
        )
        registry.update_status(value["job_id"], status)
        return value["job_id"]

    job("build-primary", "claude", "old-model", status="exited")
    current_id = job("build-primary", "codex", "retry-model")
    job("setup", "wrong-card", "wrong-model")
    job("build-primary", "wrong-repo", "wrong-model", repo="other/repo")
    job("build-primary", "wrong-phase", "wrong-model", phase="review")

    actual = manager.workflow_status_entry(registry, run)
    (row,) = slices_from_status({"attention": [actual]})
    assert (row.executor, row.model, row.job_id, row.card) == (
        "codex", "retry-model", current_id, "build-primary",
    )
    assert "執行中 · codex · retry-model" in all_text(build_jobs_nodes(group_job_rows((row,))))
    in_flight = slices_from_status({"in_flight": manager_daemon._in_flight_status(registry)})
    current = next(row for row in in_flight if row.job_id == current_id)
    assert (current.executor, current.model) == ("codex", "retry-model")

    registry.update_status(current_id, "exited")
    (last,) = slices_from_status({"attention": [manager.workflow_status_entry(registry, run)]})
    text = all_text(build_jobs_nodes(group_job_rows((last,))))
    assert "上次執行 · codex · retry-model" in text
    assert "執行中" not in text


def test_same_work_id_in_different_repositories_keeps_separate_identity():
    first, second = workflow(), workflow()
    second.update(repo="other/repo", executor="other-executor", model="other-model")
    rows = slices_from_status({"attention": [first, second]})
    assert len(rows) == 2
    assert {(row.repo, row.executor, row.model) for row in rows} == {
        ("example/cortex", "codex", "gpt-test"),
        ("other/repo", "other-executor", "other-model"),
    }


class IdentityApp(App):
    def compose(self) -> ComposeResult:
        yield JobsPanel(id="jobs")


class IdentityRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_preserves_full_model_as_literal_text_in_narrow_panel(self):
        # Losing model from the projection cache, interpreting markup, or replacing
        # the full detail with the shortened headline must fail this test.
        app = IdentityApp()
        async with app.run_test(size=(48, 18)) as pilot:
            panel = app.query_one(JobsPanel)
            item = workflow()
            panel.set_groups(group_job_rows(slices_from_status({"attention": [item]})))
            await pilot.pause()
            item["executor"] = "新-provider"
            item["model"] = "model-[bold]literal[/bold]-very-long-version-123456789"
            item["identity_source"] = "last-execution"
            item["execution_state"] = "exited"
            panel.set_groups(group_job_rows(slices_from_status({"attention": [item]})))
            await pilot.pause()
            row = panel.root.children[0]
            row.expand()
            await pilot.pause()
            text = "\n".join(str(child.label) for child in row.children)
            assert "上次執行 · 新-provider · model-[bold]literal[/bold]-very-long-version-123456789" in text
            assert "gpt-test" not in text
