"""Operator projections must not turn absent authority into execution or success."""

import io
import json

import pytest

from paulshaclaw.bot.listener import TelegramApiClient, TelegramListener
from paulshaclaw.bot.telegram import TelegramCommandRouter
from paulshaclaw.cockpit.app import group_job_rows, jobs_counts_summary, slices_from_status
from paulshaclaw.cockpit.jobs_panel import build_jobs_nodes, status_style
from paulshaclaw.core.config import AppConfig, CoordinatorSettings
from paulshaclaw.core.daemon import PaulShiaBroDaemon


@pytest.mark.parametrize("section,fields", [
    ("in_flight", {"slice_id": "task-build"}),
    ("in_flight", {"kind": "workflow_run", "work_id": "task", "current_phase": "build"}),
    ("slices", {"slice_id": "task-build"}),
    ("recent_done", {"slice_id": "task-build"}),
])
@pytest.mark.parametrize("missing", [None, "", " ", 0])
def test_absent_authoritative_state_is_unknown(section, fields, missing):
    # A running/done fallback would fabricate activity/success for this snapshot.
    item = dict(fields, state=missing, slice_state=missing, gate_state=missing, gate_status=missing)
    (row,) = slices_from_status({section: [item]})
    assert row.state == "unknown"
    assert row.display_state == "unknown"
    (node,) = build_jobs_nodes(group_job_rows((row,), axis="project"), axis="project")
    assert node.segments[0][1] == status_style("unknown")[1]


@pytest.mark.parametrize("state", ["submitted", "running", "blocked", "failed", "completed"])
def test_explicit_live_state_is_not_reinterpreted(state):
    (row,) = slices_from_status({"in_flight": [{"slice_id": "task-build", "state": state}]})
    assert row.state == state
    assert row.display_state == state
    assert jobs_counts_summary((row,)) == "1 件"


@pytest.mark.parametrize("state", ["failed", "error"])
def test_recent_failure_keeps_failure_label_and_color(state):
    rows = slices_from_status({"recent_done": [{"slice_id": "task-build", "gate_status": state}]})
    (node,) = build_jobs_nodes(group_job_rows(rows, axis="project"), axis="project")
    assert state in "".join(text for text, _ in node.children[0].segments)
    assert node.children[0].segments[0][1] == status_style(state)[1]
    assert jobs_counts_summary(rows) == "0 件"


def test_archive_preserves_gate_result_without_becoming_live_work():
    rows = slices_from_status({"recent_done": [{
        "slice_id": "task-build", "gate_status": "passed", "run_status": "archived",
    }]})
    (node,) = build_jobs_nodes(group_job_rows(rows, axis="project"), axis="project")
    text = "".join(text for text, _ in node.children[0].segments)
    assert "archived" in text
    assert "已完成" in text
    assert jobs_counts_summary(rows) == "0 件"


def test_archived_attention_keeps_lifecycle_and_pending_decision():
    (row,) = slices_from_status({"recent_done": [{
        "slice_id": "task-build", "gate_status": "needs_human", "run_status": "archived",
    }]})
    assert row.display_state == "archived · 待裁決"


def make_router(snapshot):
    class SnapshotReader:
        def read_status(self):
            return snapshot

    config = AppConfig("test", "example", (1,), CoordinatorSettings("build", None, {}), ())
    daemon = PaulShiaBroDaemon(config, coordinator=object(), manager_client=SnapshotReader())
    return TelegramCommandRouter(daemon)


def test_bot_exposes_attention_reason_and_available_decision():
    router = make_router({
        "updated_at": "2026-10-15T00:00:00Z",
        "attention": [{
            "kind": "workflow_run", "work_id": "task", "slice_state": "needs_human",
            "blocking_reason": {"reason": "verification_failed", "detail": "test failed"},
            "next_actions": ["retry-verify"],
            "next_step_hint": "inspect verification evidence",
        }],
    })
    message = router.handle_message(user_id=1, text="/manager status")["message"]
    assert "task(needs_human)" in message
    assert "test failed" in message
    assert "retry-verify" in message
    assert "inspect verification evidence" in message
    assert "2026-10-15T00:00:00Z" in message


def test_bot_preserves_live_history_and_unknown_states():
    router = make_router({
        "in_flight": [{"slice_id": state, "state": state} for state in
                      ("submitted", "running", "blocked", "failed", "completed")]
                     + [{"slice_id": "missing", "state": ""}],
        "recent_done": [{"slice_id": "history", "gate_status": "passed", "run_status": "archived"}],
    })
    message = router.handle_message(user_id=1, text="/manager status")["message"]
    for state in ("submitted", "running", "blocked", "failed", "completed"):
        assert f"{state}({state})" in message
    assert "missing(unknown)" in message
    assert "history(passed)" in message
    assert "run_status=archived" in message


@pytest.mark.parametrize("payload", [{}, {"status": "", "result": {}}, {"status": None}])
def test_empty_tick_record_does_not_report_done(payload):
    daemon = make_router({}).daemon
    message = daemon._format_manager_tick_result("request", payload)
    assert "manager tick: unknown" in message
    assert "done" not in message
    assert "unknown" in message.splitlines()[-1]


def test_submitted_tick_without_completion_stays_queued():
    assert make_router({}).daemon._format_manager_tick_result("request", None) == "queued, check /manager status"


def test_failed_tick_without_reason_explicitly_reports_unknown():
    message = make_router({}).daemon._format_manager_tick_result("request", {"status": "error"})
    assert "manager tick: error" in message
    assert "error: unknown" in message


def test_bot_attention_without_reason_keeps_unknown_visible():
    router = make_router({"attention": [{"slice_id": "task-build", "job_state": "failed"}]})
    message = router.handle_message(user_id=1, text="/manager status")["message"]
    assert "task-build(failed) reason=unknown" in message


@pytest.mark.parametrize("text", ["failure details\n" * 700, "蝦🦞 &lt;failed&gt; <literal>\n" * 400], ids=["ascii", "unicode-plain-text"])
def test_long_manager_reply_reaches_transport_as_lossless_plain_text(text):
    requests = []

    def opener(request, timeout):
        payload = json.loads(request.data)
        # Exercise the real API serializer; only the remote HTTP boundary is fake.
        requests.append(payload)
        return io.BytesIO(b'{"ok": true, "result": {"message_id": 1}}')

    listener = TelegramListener(client=TelegramApiClient("test", opener=opener), router=make_router({}))
    listener._safe_send(chat_id=1, text=text)
    assert len(requests) > 1
    assert "".join(request["text"] for request in requests) == text
    assert all(0 < len(request["text"].encode("utf-16-le")) // 2 <= 4096 for request in requests)
    assert all(request["chat_id"] == 1 and "parse_mode" not in request and "entities" not in request for request in requests)
