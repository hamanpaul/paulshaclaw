"""#275：驗證 bro-queue 積壓超時告警（`bro_queue_alert` + `bro_queue.list_backlogs`）。

核心情境：
- 門檻未到不告警
- 超過門檻告警一次
- 同一筆積壓不重複告警（去重）
- 佇列前進／清空後狀態重置，新最前筆可再次告警
- 告警送出失敗不影響既有流程（吞例外）
- `list_backlogs` 為唯讀，不改動佇列檔
"""
from __future__ import annotations

import pytest

from paulshaclaw.core import bro_queue, bro_queue_alert
from paulshaclaw.core.bro_queue_alert import BroQueueAlerter, alert_threshold_seconds, format_alert


@pytest.fixture(autouse=True)
def _isolated_state_root(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(tmp_path / "agents"))


class _FakeSender:
    def __init__(self, *, raises: bool = False) -> None:
        self.sent: list[dict[str, object]] = []
        self.raises = raises

    def send_message(self, *, chat_id: int, text: str) -> None:
        if self.raises:
            raise RuntimeError("telegram down")
        self.sent.append({"chat_id": chat_id, "text": text})


class _FakeBindings:
    def __init__(self, mapping: dict[int, int] | None = None) -> None:
        self.mapping = mapping or {}

    def lookup_chat_id(self, user_id: int) -> int | None:
        return self.mapping.get(user_id)


# ---------------------------------------------------------------------------
# list_backlogs 唯讀 API
# ---------------------------------------------------------------------------


def test_list_backlogs_empty_when_no_queue_dir():
    assert bro_queue.list_backlogs() == []


def test_list_backlogs_lists_each_pane_head_pending_seconds(monkeypatch):
    monkeypatch.setattr(bro_queue.time, "time", lambda: 1000.0)
    bro_queue.enqueue("%7", "[bro:1] first")
    bro_queue.enqueue("%7", "[bro:1] second")
    bro_queue.enqueue("%9", "[bro:2] other")

    backlogs = bro_queue.list_backlogs(now=lambda: 1000.0)

    by_pane = {b.pane_id: b for b in backlogs}
    assert set(by_pane) == {"%7", "%9"}
    assert by_pane["%7"].remaining == 2
    assert by_pane["%7"].head_message == "[bro:1] first"
    assert by_pane["%7"].head_queued_at == 1000.0
    assert by_pane["%7"].pending_seconds == 0.0
    assert by_pane["%9"].remaining == 1


def test_list_backlogs_does_not_mutate_queue_files():
    bro_queue.enqueue("%7", "[bro:1] hello")
    before = bro_queue._read_entries(bro_queue.queue_file("%7"))

    bro_queue.list_backlogs()

    after = bro_queue._read_entries(bro_queue.queue_file("%7"))
    assert before == after
    assert len(after) == 1


def test_list_backlogs_skips_empty_queue_files():
    # flush 送達後佇列檔會被清空／刪除；殘留空檔不應列入積壓。
    bro_queue.enqueue("%7", "[bro:1] hello")
    bro_queue.flush(
        "%7",
        send=lambda pane_id, message: True,
        capture=lambda pane_id: "[bro:1] hello",
    )
    assert bro_queue.list_backlogs() == []


# ---------------------------------------------------------------------------
# 門檻與告警判斷
# ---------------------------------------------------------------------------


def test_no_alert_when_backlog_under_threshold():
    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 100.0,
        list_backlogs=lambda **kw: [
            bro_queue.PaneBacklog(
                pane_id="%7", remaining=1, head_queued_at=50.0,
                head_message="x", pending_seconds=50.0,
            ),
        ],
    )

    alerter.check_and_alert()

    sender = alerter.sender
    assert sender.sent == []  # type: ignore[attr-defined]


def test_alert_once_when_over_threshold():
    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 1000.0,
        list_backlogs=lambda **kw: [
            bro_queue.PaneBacklog(
                pane_id="%7", remaining=2, head_queued_at=100.0,
                head_message="[bro:1] stuck", pending_seconds=900.0,
            ),
        ],
    )

    alerter.check_and_alert()

    sender = alerter.sender
    assert len(sender.sent) == 1  # type: ignore[attr-defined]
    assert sender.sent[0]["chat_id"] == 1001  # type: ignore[attr-defined]
    assert "積壓超時" in sender.sent[0]["text"]  # type: ignore[attr-defined]


def test_same_backlog_does_not_re_alert():
    backlog = bro_queue.PaneBacklog(
        pane_id="%7", remaining=1, head_queued_at=100.0,
        head_message="[bro:1] stuck", pending_seconds=900.0,
    )
    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 1000.0,
        list_backlogs=lambda **kw: [backlog],
    )

    alerter.check_and_alert()
    alerter.check_and_alert()  # 同一筆，第二次不應再送

    sender = alerter.sender
    assert len(sender.sent) == 1  # type: ignore[attr-defined]


def test_queue_advances_resets_dedup_and_new_head_can_alert():
    # 第一筆積壓告警後，佇列前進到第二筆（不同 queued_at）才允許再告警。
    head_a = bro_queue.PaneBacklog(
        pane_id="%7", remaining=2, head_queued_at=100.0,
        head_message="a", pending_seconds=900.0,
    )
    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 2000.0,
        list_backlogs=lambda **kw: [head_a],
    )
    alerter.check_and_alert()
    assert len(alerter.sender.sent) == 1  # type: ignore[attr-defined]

    head_b = bro_queue.PaneBacklog(
        pane_id="%7", remaining=1, head_queued_at=1300.0,
        head_message="b", pending_seconds=700.0,
    )
    alerter._list_backlogs = lambda **kw: [head_b]  # type: ignore[assignment]
    alerter.check_and_alert()

    assert len(alerter.sender.sent) == 2  # type: ignore[attr-defined]


def test_queue_clears_resets_dedup():
    backlog = bro_queue.PaneBacklog(
        pane_id="%7", remaining=1, head_queued_at=100.0,
        head_message="x", pending_seconds=900.0,
    )
    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 1000.0,
        list_backlogs=lambda **kw: [backlog],
    )
    alerter.check_and_alert()
    assert len(alerter.sender.sent) == 1  # type: ignore[attr-defined]

    # 佇列清空 → 沒有積壓
    alerter._list_backlogs = lambda **kw: []  # type: ignore[assignment]
    alerter.check_and_alert()
    assert len(alerter.sender.sent) == 1  # type: ignore[attr-defined]

    # 同一筆重新積壓超過門檻 → 可再次告警（dedup 已重置）
    backlog2 = bro_queue.PaneBacklog(
        pane_id="%7", remaining=1, head_queued_at=2000.0,
        head_message="y", pending_seconds=900.0,
    )
    alerter._list_backlogs = lambda **kw: [backlog2]  # type: ignore[assignment]
    alerter.check_and_alert()
    assert len(alerter.sender.sent) == 2  # type: ignore[attr-defined]


def test_alert_send_failure_does_not_raise():
    alerter = BroQueueAlerter(
        sender=_FakeSender(raises=True),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 1000.0,
        list_backlogs=lambda **kw: [
            bro_queue.PaneBacklog(
                pane_id="%7", remaining=1, head_queued_at=100.0,
                head_message="x", pending_seconds=900.0,
            ),
        ],
    )

    # 吞掉例外，不外炸
    alerter.check_and_alert()
    # 仍標記為已告警，避免下一輪狂重試
    assert alerter._alerted_heads == {("%7", 100.0)}


def test_no_alert_when_no_chat_binding():
    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings(),  # 查無綁定
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 1000.0,
        list_backlogs=lambda **kw: [
            bro_queue.PaneBacklog(
                pane_id="%7", remaining=1, head_queued_at=100.0,
                head_message="x", pending_seconds=900.0,
            ),
        ],
    )

    alerter.check_and_alert()

    sender = alerter.sender
    assert sender.sent == []  # type: ignore[attr-defined]


def test_list_backlogs_read_error_does_not_raise():
    def boom(**kw):
        raise OSError("disk gone")

    alerter = BroQueueAlerter(
        sender=_FakeSender(),
        bindings=_FakeBindings({7: 1001}),
        allowed_user_ids=[7],
        threshold_seconds=600.0,
        now=lambda: 1000.0,
        list_backlogs=boom,
    )

    alerter.check_and_alert()  # 不外炸


# ---------------------------------------------------------------------------
# format_alert / alert_threshold_seconds
# ---------------------------------------------------------------------------


def test_format_alert_lists_each_pane_minutes():
    backlogs = [
        bro_queue.PaneBacklog(
            pane_id="%7", remaining=3, head_queued_at=100.0,
            head_message="x", pending_seconds=900.0,
        ),
        bro_queue.PaneBacklog(
            pane_id="%9", remaining=1, head_queued_at=100.0,
            head_message="y", pending_seconds=650.0,
        ),
    ]
    text = format_alert(backlogs, threshold_seconds=600.0)

    assert "門檻 10 分鐘" in text
    assert "pane %7" in text
    assert "15 分鐘" in text  # 900 // 60
    assert "pane %9" in text


def test_alert_threshold_seconds_default_when_unset(monkeypatch):
    monkeypatch.delenv("PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS", raising=False)
    assert alert_threshold_seconds() == 600.0


def test_alert_threshold_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS", "120")
    assert alert_threshold_seconds() == 120.0


def test_alert_threshold_seconds_falls_back_on_invalid(monkeypatch):
    monkeypatch.setenv("PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS", "not-a-number")
    assert alert_threshold_seconds() == 600.0


def test_alert_threshold_seconds_falls_back_on_nonpositive(monkeypatch):
    monkeypatch.setenv("PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS", "0")
    assert alert_threshold_seconds() == 600.0

# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 秒"),
        (30, "30 秒"),
        (59, "59 秒"),
        (60, "1 分鐘"),
        (90, "1 分 30 秒"),
        (600, "10 分鐘"),
        (-5, "0 秒"),
    ],
)
def test_format_duration_avoids_zero_minute_labels(seconds, expected):
    # 門檻可由 env 設成任意正值；直接 // 60 會讓 30 秒顯示成「0 分鐘」而誤導。
    assert bro_queue_alert.format_duration(seconds) == expected


def test_format_alert_uses_second_granularity_for_short_threshold():
    backlogs = [
        bro_queue.PaneBacklog(
            pane_id="%7",
            remaining=1,
            head_queued_at=1000.0,
            head_message="[bro:1] hi",
            pending_seconds=45.0,
        )
    ]
    text = format_alert(backlogs, threshold_seconds=30.0)
    assert "門檻 30 秒未消化" in text
    assert "已等待 45 秒" in text
